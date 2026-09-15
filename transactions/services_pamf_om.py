"""Import des transactions PAMF (base CBS, marchand Orange Money) pour une date donnee.

Miroir de services_pamf.py (MVOLA) - cf. CLAUDE.md.
"""

from django.db import transaction

from .cbs import fetch_transactions_pamf_om
from .models import ImportRequeteOM, TransactionPamfOM


@transaction.atomic
def importer_transactions_pamf_om(date_requete, user):
    """Interroge le CBS (marchand Orange Money) pour `date_requete`, insere les nouvelles lignes
    dans TransactionPamfOM.

    Retourne l'ImportRequeteOM cree. En cas d'erreur de connexion/requete, l'import est marque en
    echec avec le message d'erreur, sans lever d'exception vers l'appelant.
    """
    import_obj = ImportRequeteOM.objects.create(
        date_requete=date_requete,
        executee_par=user,
        statut=ImportRequeteOM.Statut.ECHEC,
    )

    try:
        lignes = fetch_transactions_pamf_om(date_requete)
    except Exception as exc:
        import_obj.message_erreur = str(exc)
        import_obj.save(update_fields=['message_erreur'])
        return import_obj

    # transid_om n'est pas unique (cf. TransactionPamfOM) : un paiement marchand Orange Money
    # peut etre scinde cote CBS sur plusieurs prets (plusieurs postings/rAutotransactionID pour
    # un meme RequestID). La cle de dedoublonnage est donc la paire (transid_om,
    # rAutotransactionID), pas transid_om seul.
    transids = [str(ligne['TRANSID_ORANGE_MONEY']) for ligne in lignes]
    deja_existants = set(
        TransactionPamfOM.objects.filter(transid_om__in=transids)
        .values_list('transid_om', 'r_autotransaction_id')
    )

    a_inserer = []
    vus_dans_le_lot = set()
    for ligne in lignes:
        transid = str(ligne['TRANSID_ORANGE_MONEY'])
        r_autotransaction_id = str(ligne['rAutotransactionID']) if ligne['rAutotransactionID'] is not None else ''
        cle = (transid, r_autotransaction_id)
        if cle in deja_existants or cle in vus_dans_le_lot:
            continue
        vus_dans_le_lot.add(cle)
        # rAutotransactionID/Time sont NULL quand la ligne apiLog n'a pas (encore) de
        # correspondance dans mcTransaction (left join) : la requete a atteint le CBS (trace
        # apiLog) mais n'a pas ete traitee -> is_sucess=0, ticket Aspekt recommande.
        a_inserer.append(TransactionPamfOM(
            r_autotransaction_id=r_autotransaction_id,
            posting_date=ligne['postingDate'],
            time=str(ligne['Time']) if ligne.get('Time') is not None else '',
            note=ligne.get('Note') or '',
            transid_om=transid,
            response_body=ligne.get('responseBody') or '',
            montant=ligne.get('Amount'),
            is_success=bool(ligne.get('is_sucess', 1)),
            import_requete=import_obj,
        ))

    TransactionPamfOM.objects.bulk_create(a_inserer)

    import_obj.statut = ImportRequeteOM.Statut.SUCCES
    import_obj.nb_lignes = len(lignes)
    import_obj.nb_doublons = len(lignes) - len(a_inserer)
    import_obj.save(update_fields=['statut', 'nb_lignes', 'nb_doublons'])
    return import_obj
