"""Moteur de rapprochement Orange Money (OM) / PAMF, declenche manuellement par date.

Miroir de services_rapprochement.py (MVOLA) - cf. CLAUDE.md. Le fichier XLS OM doit deja avoir
ete importe pour la date demandee ; la requete CBS (marchand OM) est alors declenchee
automatiquement, puis les deux jeux de donnees sont rapproches sur transid_om.

Relancer une date deja traitee reinitialise completement ses resultats (meme choix assume que
pour MVOLA, cf. CLAUDE.md - Decisions prises) : les ResultatRapprochementOM existants sont
supprimes, ce qui supprime en cascade les EcartOM et tout leur historique, avant de tout
recalculer a neuf.
"""

from collections import defaultdict

from django.db import transaction as db_transaction

from .models import (
    ImportFichierOM,
    ImportRequeteOM,
    RapprochementOM,
    ResultatRapprochementOM,
    TransactionOM,
    TransactionPamfOM,
)
from .services_pamf_om import importer_transactions_pamf_om
from .services_rapprochement import _verifier_journee_cbs_terminee


class FichierOMNonImporte(Exception):
    """Le fichier XLS Orange Money de la date demandee n'a pas encore ete importe."""


def _obtenir_orphelines_om_anterieures(date_cible, transids):
    """Retourne les transids qui sont des orphelines OM d'une date strictement anterieure."""
    if not transids:
        return set()

    orphelines_anterieures = ResultatRapprochementOM.objects.filter(
        rapprochement__date__lt=date_cible,
        statut__in=[
            ResultatRapprochementOM.Statut.ORPHELINE_OM,
            ResultatRapprochementOM.Statut.TRANSACTION_REJOUEE,
        ],
        transid_om__in=transids,
    ).values_list('transid_om', flat=True).distinct()

    return set(orphelines_anterieures)


def _purger_resultats_existants_om(rapprochement):
    """Supprime les pieces jointes physiques puis tous les ResultatRapprochementOM de la date.

    Cf. services_rapprochement._purger_resultats_existants (MVOLA) - meme raisonnement : Django
    ne supprime jamais le fichier physique d'un FileField lors d'une suppression en cascade.
    """
    from ecarts.models import EcartHistoriqueOM

    historiques_avec_fichier = EcartHistoriqueOM.objects.filter(
        ecart__resultat__rapprochement=rapprochement,
    ).exclude(fichier='')
    for historique in historiques_avec_fichier:
        historique.fichier.delete(save=False)

    rapprochement.resultats.all().delete()


def _generer_ecarts_om(rapprochement):
    from ecarts.models import EcartOM

    orphelines = rapprochement.resultats.exclude(statut=ResultatRapprochementOM.Statut.SUCCESS)
    a_creer = [
        EcartOM(
            resultat=resultat,
            transid_om=resultat.transid_om,
            type_ecart=resultat.statut,
            date_transaction=rapprochement.date,
        )
        for resultat in orphelines
    ]
    EcartOM.objects.bulk_create(a_creer, batch_size=200)
    return a_creer


@db_transaction.atomic
def lancer_rapprochement_om(date_cible, user):
    """Lance (ou relance) le rapprochement Orange Money pour `date_cible`. Retourne le
    RapprochementOM. Cf. lancer_rapprochement (MVOLA) pour le detail du raisonnement."""
    if not ImportFichierOM.objects.filter(
        date_fichier=date_cible, statut=ImportFichierOM.Statut.SUCCES
    ).exists():
        raise FichierOMNonImporte(
            f"Le fichier Orange Money du {date_cible.strftime('%d/%m/%Y')} n'a pas encore ete importe."
        )

    _verifier_journee_cbs_terminee(date_cible)

    rapprochement, _ = RapprochementOM.objects.get_or_create(date=date_cible)
    rapprochement.statut = RapprochementOM.Statut.EN_COURS
    rapprochement.lance_par = user
    rapprochement.message_erreur = ''
    rapprochement.save()

    import_pamf = importer_transactions_pamf_om(date_cible, user)
    if import_pamf.statut == ImportRequeteOM.Statut.ECHEC:
        rapprochement.statut = RapprochementOM.Statut.ECHEC
        rapprochement.message_erreur = import_pamf.message_erreur
        rapprochement.save(update_fields=['statut', 'message_erreur'])
        return rapprochement

    _purger_resultats_existants_om(rapprochement)

    om_par_id = {t.transid_om: t for t in TransactionOM.objects.filter(date_trans__date=date_cible)}
    pamf_groupes = defaultdict(list)
    for t in TransactionPamfOM.objects.filter(posting_date=date_cible):
        pamf_groupes[t.transid_om].append(t)
    tous_ids = set(om_par_id) | set(pamf_groupes)

    # Detecter les orphelines PAMF qui correspondent a une orpheline OM d'une date anterieure
    orphelines_pamf_ids = {transid for transid in tous_ids if not om_par_id.get(transid)}
    orphelines_om_anterieures = _obtenir_orphelines_om_anterieures(date_cible, orphelines_pamf_ids)

    nb_success = nb_orph_om = nb_orph_pamf = nb_doublons_pamf = nb_rejouees = 0
    a_creer = []
    for transid in tous_ids:
        om = om_par_id.get(transid)
        groupe_pamf = pamf_groupes.get(transid, [])

        if len(groupe_pamf) > 1:
            # Plusieurs postings CBS pour ce transid (paiement marchand scinde sur plusieurs
            # prets, cf. CLAUDE.md) : ambigu, on ne tranche pas automatiquement - l'agent choisit
            # le posting de reference depuis l'ecran de l'ecart (cf. action_recommandee).
            statut = ResultatRapprochementOM.Statut.DOUBLON_PAMF
            pamf = None
            nb_doublons_pamf += 1
        else:
            pamf = groupe_pamf[0] if groupe_pamf else None
            if om and pamf and pamf.is_success:
                statut = ResultatRapprochementOM.Statut.SUCCESS
                nb_success += 1
            elif om:
                # Orpheline OM : soit une ligne PAMF existe mais en echec (ticket Aspekt a
                # creer), soit aucune ligne PAMF (rollback recommande cote OM). Cf.
                # ResultatRapprochementOM.action_recommandee et CLAUDE.md.
                statut = ResultatRapprochementOM.Statut.ORPHELINE_OM
                nb_orph_om += 1
            elif pamf and not pamf.is_success:
                # Absente cote OM ET en echec cote PAMF : rien a rapprocher ni a regulariser.
                # Exclue completement du resultat (cf. CLAUDE.md, meme regle que MVOLA).
                continue
            else:
                # Orpheline PAMF : verifier si elle correspond a une orpheline OM d'une date
                # anterieure (transaction rejouee).
                if transid in orphelines_om_anterieures:
                    statut = ResultatRapprochementOM.Statut.TRANSACTION_REJOUEE
                    nb_rejouees += 1
                else:
                    statut = ResultatRapprochementOM.Statut.ORPHELINE_PAMF
                    nb_orph_pamf += 1

        a_creer.append(ResultatRapprochementOM(
            rapprochement=rapprochement, transid_om=transid,
            statut=statut, transaction_om=om, transaction_pamf=pamf,
        ))

    # Insertion en bulk plutot qu'une requete par transaction (cf. CLAUDE.md).
    ResultatRapprochementOM.objects.bulk_create(a_creer, batch_size=200)

    rapprochement.nb_om = len(om_par_id)
    rapprochement.nb_pamf = len(pamf_groupes)
    rapprochement.nb_success = nb_success
    rapprochement.nb_orphelines_om = nb_orph_om
    rapprochement.nb_orphelines_pamf = nb_orph_pamf
    rapprochement.nb_doublons_pamf = nb_doublons_pamf
    rapprochement.nb_transactions_rejouees = nb_rejouees
    rapprochement.statut = RapprochementOM.Statut.TERMINE
    rapprochement.save()

    nouveaux_ecarts = _generer_ecarts_om(rapprochement)
    if nouveaux_ecarts:
        from ecarts.notifications import notifier_nouveaux_ecarts_om
        db_transaction.on_commit(lambda: notifier_nouveaux_ecarts_om(rapprochement, nouveaux_ecarts))

    return rapprochement
