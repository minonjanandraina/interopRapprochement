"""Moteur de rapprochement MVOLA / PAMF, declenche manuellement par date.

Cf. CLAUDE.md - Decisions prises : le CSV MVOLA doit deja avoir ete importe pour la date
demandee ; la requete CBS (import PAMF) est alors declenchee automatiquement, puis les deux
jeux de donnees sont rapproches sur TRANSID_MVOLA.
"""

from django.db import transaction as db_transaction

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


def _generer_ecarts(rapprochement):
    from ecarts.models import Ecart

    orphelines = rapprochement.resultats.exclude(statut=ResultatRapprochement.Statut.SUCCESS)
    for resultat in orphelines:
        Ecart.objects.get_or_create(
            resultat=resultat,
            defaults={
                'transid_mvola': resultat.transid_mvola,
                'type_ecart': resultat.statut,
                'date_transaction': rapprochement.date,
            },
        )


@db_transaction.atomic
def lancer_rapprochement(date_cible, user):
    """Lance (ou relance) le rapprochement pour `date_cible`. Retourne le Rapprochement."""
    if not ImportFichierMvola.objects.filter(
        date_fichier=date_cible, statut=ImportFichierMvola.Statut.SUCCES
    ).exists():
        raise CsvMvolaNonImporte(
            f"Le fichier CSV MVOLA du {date_cible.strftime('%d/%m/%Y')} n'a pas encore ete importe."
        )

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

    mvola_par_id = {t.transid_mvola: t for t in TransactionMvola.objects.filter(date_trans__date=date_cible)}
    pamf_par_id = {t.transid_mvola: t for t in TransactionPamf.objects.filter(posting_date=date_cible)}
    tous_ids = set(mvola_par_id) | set(pamf_par_id)

    rapprochement.resultats.exclude(transid_mvola__in=tous_ids).delete()

    nb_success = nb_orph_mvola = nb_orph_pamf = 0
    for transid in tous_ids:
        mvola = mvola_par_id.get(transid)
        pamf = pamf_par_id.get(transid)
        if mvola and pamf:
            statut = ResultatRapprochement.Statut.SUCCESS
            nb_success += 1
        elif mvola:
            statut = ResultatRapprochement.Statut.ORPHELINE_MVOLA
            nb_orph_mvola += 1
        else:
            statut = ResultatRapprochement.Statut.ORPHELINE_PAMF
            nb_orph_pamf += 1

        ResultatRapprochement.objects.update_or_create(
            rapprochement=rapprochement, transid_mvola=transid,
            defaults={'statut': statut, 'transaction_mvola': mvola, 'transaction_pamf': pamf},
        )

    rapprochement.nb_mvola = len(mvola_par_id)
    rapprochement.nb_pamf = len(pamf_par_id)
    rapprochement.nb_success = nb_success
    rapprochement.nb_orphelines_mvola = nb_orph_mvola
    rapprochement.nb_orphelines_pamf = nb_orph_pamf
    rapprochement.statut = Rapprochement.Statut.TERMINE
    rapprochement.save()

    _generer_ecarts(rapprochement)
    return rapprochement
