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

    # transid_mvola n'est pas unique (cf. TransactionPamf) : un paiement marchand peut etre
    # scinde cote CBS sur plusieurs prets (plusieurs postings/rAutotransactionID pour un meme
    # RequestID). La cle de dedoublonnage est donc la paire (transid_mvola, rAutotransactionID),
    # pas transid_mvola seul.
    transids = [str(ligne['TRANSID_MVOLA']) for ligne in lignes]
    deja_existants = set(
        TransactionPamf.objects.filter(transid_mvola__in=transids)
        .values_list('transid_mvola', 'r_autotransaction_id')
    )

    a_inserer = []
    vus_dans_le_lot = set()
    for ligne in lignes:
        transid = str(ligne['TRANSID_MVOLA'])
        r_autotransaction_id = str(ligne['rAutotransactionID']) if ligne['rAutotransactionID'] is not None else ''
        cle = (transid, r_autotransaction_id)
        if cle in deja_existants or cle in vus_dans_le_lot:
            continue
        vus_dans_le_lot.add(cle)
        # rAutotransactionID/Time sont NULL quand la ligne apiLog n'a pas (encore) de
        # correspondance dans mcTransaction (cf. CLAUDE.md - left join) : la requete a atteint
        # le CBS (trace apiLog) mais n'a pas ete traitee -> is_sucess=0, ticket Aspekt recommande.
        a_inserer.append(TransactionPamf(
            r_autotransaction_id=r_autotransaction_id,
            posting_date=ligne['postingDate'],
            time=str(ligne['Time']) if ligne.get('Time') is not None else '',
            note=ligne.get('Note') or '',
            transid_mvola=transid,
            response_body=ligne.get('responseBody') or '',
            apiservice=ligne.get('apiservice'),
            path=ligne.get('path') or '',
            body=ligne.get('body') or '',
            is_success=bool(ligne.get('is_sucess', 1)),
            import_requete=import_obj,
        ))

    TransactionPamf.objects.bulk_create(a_inserer)

    import_obj.statut = ImportRequetePamf.Statut.SUCCES
    import_obj.nb_lignes = len(lignes)
    import_obj.nb_doublons = len(lignes) - len(a_inserer)
    import_obj.save(update_fields=['statut', 'nb_lignes', 'nb_doublons'])
    return import_obj
