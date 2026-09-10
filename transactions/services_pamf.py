"""Import des transactions PAMF (base CBS) pour une date donnee."""

from django.db import transaction

from .cbs import fetch_transactions_pamf
from .models import ImportRequetePamf, TransactionPamf


@transaction.atomic
def importer_transactions_pamf(date_requete, user):
    """Interroge le CBS pour `date_requete`, insere les nouvelles lignes dans TransactionPamf.

    Retourne l'ImportRequetePamf cree. En cas d'erreur de connexion/requete, l'import est
    marque en echec avec le message d'erreur, sans lever d'exception vers l'appelant.
    """
    import_obj = ImportRequetePamf.objects.create(
        date_requete=date_requete,
        executee_par=user,
        statut=ImportRequetePamf.Statut.ECHEC,
    )

    try:
        lignes = fetch_transactions_pamf(date_requete)
    except Exception as exc:
        import_obj.message_erreur = str(exc)
        import_obj.save(update_fields=['message_erreur'])
        return import_obj

    transids = [str(ligne['TRANSID_MVOLA']) for ligne in lignes]
    deja_existants = set(
        TransactionPamf.objects.filter(transid_mvola__in=transids).values_list('transid_mvola', flat=True)
    )

    a_inserer = []
    for ligne in lignes:
        transid = str(ligne['TRANSID_MVOLA'])
        if transid in deja_existants:
            continue
        a_inserer.append(TransactionPamf(
            r_autotransaction_id=str(ligne['rAutotransactionID']),
            posting_date=ligne['postingDate'],
            time=str(ligne.get('Time', '')),
            note=ligne.get('Note') or '',
            transid_mvola=transid,
            response_body=ligne.get('responseBody') or '',
            is_success=bool(ligne.get('is_sucess', 1)),
            import_requete=import_obj,
        ))

    TransactionPamf.objects.bulk_create(a_inserer)

    import_obj.statut = ImportRequetePamf.Statut.SUCCES
    import_obj.nb_lignes = len(lignes)
    import_obj.nb_doublons = len(lignes) - len(a_inserer)
    import_obj.save(update_fields=['statut', 'nb_lignes', 'nb_doublons'])
    return import_obj
