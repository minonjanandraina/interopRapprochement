"""Moteur de rapprochement MVOLA / PAMF, declenche manuellement par date.

Cf. CLAUDE.md - Decisions prises : le CSV MVOLA doit deja avoir ete importe pour la date
demandee ; la requete CBS (import PAMF) est alors declenchee automatiquement, puis les deux
jeux de donnees sont rapproches sur TRANSID_MVOLA.

Relancer une date deja traitee reinitialise completement ses resultats : les ResultatRapprochement
existants sont supprimes, ce qui supprime en cascade les Ecart et tout leur historique
(commentaires, tickets Aspekt, confirmations de rollback, pieces jointes) avant de tout
recalculer a neuf. C'est un choix assume (cf. Decisions prises) - le travail de regularisation
deja effectue sur une date n'est PAS conserve d'une relance a l'autre.
"""

from datetime import datetime, time

from django.db import transaction as db_transaction

from .cbs import fetch_derniere_activite
from .models import (
    ImportFichierMvola,
    ImportRequetePamf,
    Rapprochement,
    ResultatRapprochement,
    TransactionMvola,
    TransactionPamf,
)
from .services_pamf import importer_transactions_pamf


class CsvMvolaNonImporte(Exception):
    """Le CSV MVOLA de la date demandee n'a pas encore ete importe."""


class JourneeCbsNonTerminee(Exception):
    """La journee CBS de la date demandee n'est pas encore consideree comme terminee.

    Heuristique (cf. CLAUDE.md) : on lit l'horodatage de la derniere ligne loggee dans
    bagsPAMF_CBS_MC.dbo.apiLog (toutes dates/marchands confondus, la plus recente par apiLogID).
    La journee `date_cible` est consideree terminee si cet horodatage est >= `date_cible` 23:00:00.
    En cas d'echec de cette verification (CBS injoignable) ou d'absence totale de donnees dans
    apiLog, on bloque par prudence plutot que de laisser lancer un rapprochement sur une journee
    potentiellement incomplete.
    """


def _verifier_journee_cbs_terminee(date_cible):
    heure_limite = datetime.combine(date_cible, time(23, 0, 0))
    try:
        derniere_activite = fetch_derniere_activite()
    except Exception as exc:
        raise JourneeCbsNonTerminee(
            f"Impossible de verifier si la journee CBS du {date_cible.strftime('%d/%m/%Y')} "
            f"est terminee : {exc}"
        ) from exc

    if derniere_activite is None or derniere_activite < heure_limite:
        raise JourneeCbsNonTerminee(
            f"La journee CBS du {date_cible.strftime('%d/%m/%Y')} n'est pas encore terminee "
            f"(derniere activite CBS connue : "
            f"{derniere_activite.strftime('%d/%m/%Y %H:%M:%S') if derniere_activite else 'aucune'})."
        )


def _purger_resultats_existants(rapprochement):
    """Supprime les pieces jointes physiques puis tous les ResultatRapprochement de la date.

    La suppression cascade (ResultatRapprochement -> Ecart -> EcartHistorique) efface le
    traitement deja effectue. Django ne supprime jamais le fichier physique d'un FileField lors
    d'une suppression en cascade : on le fait explicitement pour ne pas laisser de fichiers
    orphelins sous media/.
    """
    from ecarts.models import EcartHistorique

    historiques_avec_fichier = EcartHistorique.objects.filter(
        ecart__resultat__rapprochement=rapprochement,
    ).exclude(fichier='')
    for historique in historiques_avec_fichier:
        historique.fichier.delete(save=False)

    rapprochement.resultats.all().delete()


def _generer_ecarts(rapprochement):
    from ecarts.models import Ecart

    orphelines = rapprochement.resultats.exclude(statut=ResultatRapprochement.Statut.SUCCESS)
    a_creer = [
        Ecart(
            resultat=resultat,
            transid_mvola=resultat.transid_mvola,
            type_ecart=resultat.statut,
            date_transaction=rapprochement.date,
        )
        for resultat in orphelines
    ]
    Ecart.objects.bulk_create(a_creer, batch_size=200)
    return a_creer


@db_transaction.atomic
def lancer_rapprochement(date_cible, user):
    """Lance (ou relance) le rapprochement pour `date_cible`. Retourne le Rapprochement.

    Relancer une date deja traitee efface et recalcule entierement ses resultats (cf. docstring
    du module) : tout traitement d'ecart deja effectue pour cette date est perdu.
    """
    if not ImportFichierMvola.objects.filter(
        date_fichier=date_cible, statut=ImportFichierMvola.Statut.SUCCES
    ).exists():
        raise CsvMvolaNonImporte(
            f"Le fichier CSV MVOLA du {date_cible.strftime('%d/%m/%Y')} n'a pas encore ete importe."
        )

    _verifier_journee_cbs_terminee(date_cible)

    rapprochement, _ = Rapprochement.objects.get_or_create(date=date_cible)
    rapprochement.statut = Rapprochement.Statut.EN_COURS
    rapprochement.lance_par = user
    rapprochement.message_erreur = ''
    rapprochement.save()

    import_pamf = importer_transactions_pamf(date_cible, user)
    if import_pamf.statut == ImportRequetePamf.Statut.ECHEC:
        rapprochement.statut = Rapprochement.Statut.ECHEC
        rapprochement.message_erreur = import_pamf.message_erreur
        rapprochement.save(update_fields=['statut', 'message_erreur'])
        return rapprochement

    _purger_resultats_existants(rapprochement)

    mvola_par_id = {t.transid_mvola: t for t in TransactionMvola.objects.filter(date_trans__date=date_cible)}
    pamf_par_id = {t.transid_mvola: t for t in TransactionPamf.objects.filter(posting_date=date_cible)}
    tous_ids = set(mvola_par_id) | set(pamf_par_id)

    nb_success = nb_orph_mvola = nb_orph_pamf = 0
    a_creer = []
    for transid in tous_ids:
        mvola = mvola_par_id.get(transid)
        pamf = pamf_par_id.get(transid)
        if mvola and pamf and pamf.is_success:
            statut = ResultatRapprochement.Statut.SUCCESS
            nb_success += 1
        elif mvola:
            # Orpheline MVOLA : soit une ligne PAMF existe mais en echec (is_success=False,
            # ticket Aspekt a creer, la requete a atteint Aspekt), soit aucune ligne PAMF
            # (rollback recommande cote MVOLA, la requete n'a pas atteint Aspekt).
            # Cf. ResultatRapprochement.action_recommandee et CLAUDE.md.
            statut = ResultatRapprochement.Statut.ORPHELINE_MVOLA
            nb_orph_mvola += 1
        elif pamf and not pamf.is_success:
            # Absente cote MVOLA ET en echec cote PAMF : aucun mouvement d'argent ni d'un cote
            # ni de l'autre (pas de debit wallet, transaction PAMF non postee) -> rien a
            # rapprocher ni a regulariser. Exclue completement du resultat (pas de
            # ResultatRapprochement, pas d'Ecart), cf. CLAUDE.md, decision du 2026-09-14.
            continue
        else:
            statut = ResultatRapprochement.Statut.ORPHELINE_PAMF
            nb_orph_pamf += 1

        a_creer.append(ResultatRapprochement(
            rapprochement=rapprochement, transid_mvola=transid,
            statut=statut, transaction_mvola=mvola, transaction_pamf=pamf,
        ))

    # Insertion en bulk plutot qu'une requete par transaction : essentiel pour rester rapide en
    # synchrone avec plusieurs centaines/milliers de lignes par jour (cf. CLAUDE.md).
    ResultatRapprochement.objects.bulk_create(a_creer, batch_size=200)

    rapprochement.nb_mvola = len(mvola_par_id)
    rapprochement.nb_pamf = len(pamf_par_id)
    rapprochement.nb_success = nb_success
    rapprochement.nb_orphelines_mvola = nb_orph_mvola
    rapprochement.nb_orphelines_pamf = nb_orph_pamf
    rapprochement.statut = Rapprochement.Statut.TERMINE
    rapprochement.save()

    nouveaux_ecarts = _generer_ecarts(rapprochement)
    if nouveaux_ecarts:
        from ecarts.notifications import notifier_nouveaux_ecarts
        db_transaction.on_commit(lambda: notifier_nouveaux_ecarts(rapprochement, nouveaux_ecarts))

    return rapprochement
