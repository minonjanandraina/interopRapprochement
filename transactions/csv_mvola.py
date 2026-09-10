"""Parsing et validation du CSV MVOLA (YYYY-MM-DD_reporting_PAMF.csv). Cf. CLAUDE.md - Source 1."""

import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import ImportFichierMvola, TransactionMvola

FILENAME_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})_reporting_PAMF\.csv$')

EXPECTED_COLUMNS = [
    'DATE_TRANS', 'TRANSID_MVOLA', 'STATE', 'MSISDN', 'PIVOT', 'SENS', 'NOM',
    'TRANSID_PARENT', 'TRANS_TYPE', 'AMOUNT', 'SOLDE_PIVOT_AVANT',
    'SOLDE_PIVOT_APRES', 'ORIGFTID', 'TYPE_OPERATION',
]


class FichierMvolaInvalide(Exception):
    """Erreur bloquante : le fichier ne peut pas etre traite (nom ou en-tete invalide)."""


def extraire_date_du_nom(nom_fichier):
    match = FILENAME_RE.match(nom_fichier)
    if not match:
        raise FichierMvolaInvalide(
            "Le nom du fichier doit respecter le format YYYY-MM-DD_reporting_PAMF.csv "
            f"(recu : '{nom_fichier}')."
        )
    try:
        return datetime.strptime(match.group(1), '%Y-%m-%d').date()
    except ValueError:
        raise FichierMvolaInvalide(f"Date invalide dans le nom du fichier '{nom_fichier}'.")


def _parse_decimal(valeur, champ, num_ligne, erreurs):
    try:
        return Decimal(valeur)
    except (InvalidOperation, TypeError):
        erreurs.append(f"Ligne {num_ligne} : valeur invalide pour {champ} ('{valeur}').")
        return None


def _parse_datetime(valeur, num_ligne, erreurs):
    try:
        naive = datetime.strptime(valeur, '%d/%m/%Y %H:%M:%S')
        return timezone.make_aware(naive)
    except (ValueError, TypeError):
        erreurs.append(f"Ligne {num_ligne} : DATE_TRANS invalide ('{valeur}').")
        return None


def _parse_lignes(fichier_django, erreurs):
    """Lit et valide chaque ligne du CSV. Retourne la liste des TransactionMvola pretes a inserer."""
    contenu = fichier_django.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(contenu), delimiter=';')

    if reader.fieldnames != EXPECTED_COLUMNS:
        raise FichierMvolaInvalide(
            "Les colonnes du fichier ne correspondent pas au format attendu.\n"
            f"Attendu : {';'.join(EXPECTED_COLUMNS)}\n"
            f"Recu : {';'.join(reader.fieldnames or [])}"
        )

    transids_vus = set()
    lignes_valides = []
    nb_lignes_lues = 0

    for num_ligne, row in enumerate(reader, start=2):
        nb_lignes_lues += 1
        transid = (row.get('TRANSID_MVOLA') or '').strip()
        if not transid:
            erreurs.append(f"Ligne {num_ligne} : TRANSID_MVOLA manquant.")
            continue
        if transid in transids_vus:
            erreurs.append(f"Ligne {num_ligne} : TRANSID_MVOLA '{transid}' en double dans le fichier (ignoree).")
            continue

        date_trans = _parse_datetime(row.get('DATE_TRANS'), num_ligne, erreurs)
        amount = _parse_decimal(row.get('AMOUNT'), 'AMOUNT', num_ligne, erreurs)
        solde_avant = _parse_decimal(row.get('SOLDE_PIVOT_AVANT'), 'SOLDE_PIVOT_AVANT', num_ligne, erreurs)
        solde_apres = _parse_decimal(row.get('SOLDE_PIVOT_APRES'), 'SOLDE_PIVOT_APRES', num_ligne, erreurs)
        if date_trans is None or amount is None or solde_avant is None or solde_apres is None:
            continue

        transids_vus.add(transid)
        lignes_valides.append(TransactionMvola(
            date_trans=date_trans,
            transid_mvola=transid,
            state=row.get('STATE', ''),
            msisdn=row.get('MSISDN', ''),
            pivot=row.get('PIVOT', ''),
            sens=row.get('SENS', ''),
            nom=row.get('NOM', ''),
            transid_parent=row.get('TRANSID_PARENT', '0'),
            trans_type=row.get('TRANS_TYPE', ''),
            amount=amount,
            solde_pivot_avant=solde_avant,
            solde_pivot_apres=solde_apres,
            origftid=row.get('ORIGFTID', ''),
            type_operation=row.get('TYPE_OPERATION', ''),
        ))

    return nb_lignes_lues, lignes_valides


@transaction.atomic
def importer_fichier_mvola(fichier_django, user):
    """Valide, parse et insere le CSV MVOLA. Retourne l'ImportFichierMvola cree."""
    nom_original = fichier_django.name
    date_fichier = extraire_date_du_nom(nom_original)

    erreurs = []
    nb_lignes_lues, lignes_valides = _parse_lignes(fichier_django, erreurs)
    fichier_django.seek(0)

    import_obj = ImportFichierMvola.objects.create(
        fichier=fichier_django,
        nom_original=nom_original,
        date_fichier=date_fichier,
        importe_par=user,
        statut=ImportFichierMvola.Statut.SUCCES,
        nb_lignes_lues=nb_lignes_lues,
        nb_erreurs=len(erreurs),
        message_erreur='\n'.join(erreurs),
    )

    transids = [ligne.transid_mvola for ligne in lignes_valides]
    deja_existants = set(
        TransactionMvola.objects.filter(transid_mvola__in=transids).values_list('transid_mvola', flat=True)
    )
    a_inserer = []
    for ligne in lignes_valides:
        if ligne.transid_mvola in deja_existants:
            continue
        ligne.import_fichier = import_obj
        a_inserer.append(ligne)

    TransactionMvola.objects.bulk_create(a_inserer)

    import_obj.nb_doublons = len(lignes_valides) - len(a_inserer)
    import_obj.nb_lignes_inserees = len(a_inserer)
    import_obj.save(update_fields=['nb_doublons', 'nb_lignes_inserees'])
    return import_obj
