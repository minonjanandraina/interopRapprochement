"""Parsing et validation du releve XLS Orange Money
(Daily-ChannelUserTransactionReport-<compte>-YYYYMMDD.xls). Cf. CLAUDE.md - Source 1 (OM).

Le fichier est un relevé de rapport avec ~22 lignes d'en-tete (metadonnees du relevé,
en-tetes de colonnes repetees a chaque section, lignes de sous-total/section 'Total'/'Solde')
avant et entre les lignes de donnees. Plutot que de reperer la position de l'en-tete (qui varie
selon le nombre de sections), on ne garde que les lignes dont la cellule "N" (colonne A) est de
type numerique xlrd : verifie sur le fichier reel, c'est le seul critere qui isole exactement les
lignes de transaction (cf. CLAUDE.md).
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import xlrd
from django.db import transaction
from django.utils import timezone

from .models import ImportFichierOM, TransactionOM

FILENAME_RE = re.compile(r'^Daily-ChannelUserTransactionReport-\d+-(\d{8})\.xls$', re.IGNORECASE)

STATUT_SUCCES = 'Succès'

# Colonnes 0-indexees du tableau (cf. CLAUDE.md - Source 1 OM).
COL_NUMERO = 0
COL_DATE = 1
COL_HEURE = 2
COL_REFERENCE = 3
COL_SERVICE = 4
COL_PAIEMENT = 5
COL_STATUT = 6
COL_MODE = 7
COL_COMPTE_TECHNIQUE = 8
COL_WALLET_AGENT = 9
COL_PSEUDO = 10
COL_MSISDN = 11
COL_WALLET_CORRESPONDANT = 12
COL_DEBIT = 13
COL_CREDIT = 14
COL_COMMISSIONS = 15

NB_COLONNES_MIN = 16


class FichierOMInvalide(Exception):
    """Erreur bloquante : le fichier ne peut pas etre traite (nom ou format invalide)."""


def extraire_date_du_nom(nom_fichier):
    match = FILENAME_RE.match(nom_fichier)
    if not match:
        raise FichierOMInvalide(
            "Le nom du fichier doit respecter le format "
            "Daily-ChannelUserTransactionReport-<compte>-YYYYMMDD.xls "
            f"(recu : '{nom_fichier}')."
        )
    try:
        return datetime.strptime(match.group(1), '%Y%m%d').date()
    except ValueError:
        raise FichierOMInvalide(f"Date invalide dans le nom du fichier '{nom_fichier}'.")


def _ouvrir_classeur(fichier_django):
    try:
        return xlrd.open_workbook(file_contents=fichier_django.read())
    except Exception as exc:
        raise FichierOMInvalide(f"Fichier XLS illisible : {exc}") from exc


def _texte(sheet, row, col):
    if col >= sheet.ncols:
        return ''
    valeur = sheet.cell_value(row, col)
    return str(valeur).strip() if valeur is not None else ''


def _parse_decimal(valeur, champ, num_ligne, erreurs, optionnel=False):
    if valeur in (None, '') and optionnel:
        return None
    try:
        return Decimal(str(valeur))
    except (InvalidOperation, TypeError, ValueError):
        erreurs.append(f"Ligne {num_ligne} : valeur invalide pour {champ} ('{valeur}').")
        return None


def _parse_date_heure(sheet, row, num_ligne, erreurs):
    try:
        date_str = sheet.cell_value(row, COL_DATE)
        heure_str = sheet.cell_value(row, COL_HEURE)
        naive = datetime.strptime(f'{date_str} {heure_str}', '%d/%m/%Y %H:%M:%S')
        return timezone.make_aware(naive)
    except (ValueError, TypeError):
        erreurs.append(f"Ligne {num_ligne} : Date/Heure invalide ('{date_str}' '{heure_str}').")
        return None


def _est_ligne_donnee(sheet, row):
    """Une ligne de transaction a sa colonne A (N) de type numerique xlrd. Toutes les autres
    lignes (en-tetes repetes, separateurs, sections, totaux/soldes) ont une colonne A vide ou
    textuelle - verifie sur le fichier reel, cf. CLAUDE.md."""
    return sheet.cell_type(row, COL_NUMERO) == xlrd.XL_CELL_NUMBER


def _parse_lignes(fichier_django, erreurs):
    """Lit et valide chaque ligne de transaction du XLS. Retourne
    (nb_lignes_lues, nb_hors_succes, lignes_valides pretes a inserer)."""
    classeur = _ouvrir_classeur(fichier_django)
    sheet = classeur.sheet_by_index(0)

    if sheet.ncols < NB_COLONNES_MIN:
        raise FichierOMInvalide(
            f"Le fichier ne contient que {sheet.ncols} colonne(s), format Orange Money attendu."
        )

    lignes_donnees = [r for r in range(sheet.nrows) if _est_ligne_donnee(sheet, r)]
    if not lignes_donnees:
        raise FichierOMInvalide("Aucune ligne de transaction trouvee dans le fichier.")

    transids_vus = set()
    lignes_valides = []
    nb_hors_succes = 0

    for num_ligne, row in enumerate(lignes_donnees, start=1):
        statut = _texte(sheet, row, COL_STATUT)
        transid = _texte(sheet, row, COL_REFERENCE)

        if statut != STATUT_SUCCES:
            nb_hors_succes += 1
            continue

        if not transid:
            erreurs.append(f"Ligne {num_ligne} (feuille, ligne {row + 1}) : reference OM manquante.")
            continue
        if transid in transids_vus:
            erreurs.append(f"Ligne {num_ligne} : reference OM '{transid}' en double dans le fichier (ignoree).")
            continue

        date_trans = _parse_date_heure(sheet, row, num_ligne, erreurs)
        montant = _parse_decimal(sheet.cell_value(row, COL_CREDIT), 'Credit', num_ligne, erreurs)
        if date_trans is None or montant is None:
            continue

        numero_ligne_brut = sheet.cell_value(row, COL_NUMERO)
        debit = _parse_decimal(sheet.cell_value(row, COL_DEBIT), 'Debit', num_ligne, erreurs, optionnel=True)
        commissions = _parse_decimal(
            sheet.cell_value(row, COL_COMMISSIONS), 'Commissions', num_ligne, erreurs, optionnel=True,
        ) if sheet.ncols > COL_COMMISSIONS else None

        transids_vus.add(transid)
        lignes_valides.append(TransactionOM(
            numero_ligne=int(numero_ligne_brut),
            date_trans=date_trans,
            transid_om=transid,
            service=_texte(sheet, row, COL_SERVICE),
            paiement=_texte(sheet, row, COL_PAIEMENT),
            statut=statut,
            mode=_texte(sheet, row, COL_MODE),
            compte_technique=_texte(sheet, row, COL_COMPTE_TECHNIQUE),
            wallet_agent=_texte(sheet, row, COL_WALLET_AGENT),
            pseudo=_texte(sheet, row, COL_PSEUDO),
            msisdn=_texte(sheet, row, COL_MSISDN),
            wallet_correspondant=_texte(sheet, row, COL_WALLET_CORRESPONDANT),
            debit=debit,
            montant=montant,
            commissions=commissions,
        ))

    return len(lignes_donnees), nb_hors_succes, lignes_valides


@transaction.atomic
def importer_fichier_om(fichier_django, user):
    """Valide, parse et insere le XLS Orange Money. Retourne l'ImportFichierOM cree."""
    nom_original = fichier_django.name
    date_fichier = extraire_date_du_nom(nom_original)

    erreurs = []
    nb_lignes_lues, nb_hors_succes, lignes_valides = _parse_lignes(fichier_django, erreurs)
    fichier_django.seek(0)

    import_obj = ImportFichierOM.objects.create(
        fichier=fichier_django,
        nom_original=nom_original,
        date_fichier=date_fichier,
        importe_par=user,
        statut=ImportFichierOM.Statut.SUCCES,
        nb_lignes_lues=nb_lignes_lues,
        nb_hors_succes=nb_hors_succes,
        nb_erreurs=len(erreurs),
        message_erreur='\n'.join(erreurs),
    )

    transids = [ligne.transid_om for ligne in lignes_valides]
    deja_existants = set(
        TransactionOM.objects.filter(transid_om__in=transids).values_list('transid_om', flat=True)
    )
    a_inserer = []
    for ligne in lignes_valides:
        if ligne.transid_om in deja_existants:
            continue
        ligne.import_fichier = import_obj
        a_inserer.append(ligne)

    TransactionOM.objects.bulk_create(a_inserer)

    import_obj.nb_doublons = len(lignes_valides) - len(a_inserer)
    import_obj.nb_lignes_inserees = len(a_inserer)
    import_obj.save(update_fields=['nb_doublons', 'nb_lignes_inserees'])
    return import_obj
