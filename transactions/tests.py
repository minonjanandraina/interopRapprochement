from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .csv_mvola import FichierMvolaInvalide, importer_fichier_mvola
from .models import ImportFichierMvola, ImportRequetePamf, TransactionMvola, TransactionPamf
from .services_pamf import importer_transactions_pamf

User = get_user_model()

HEADER = (
    'DATE_TRANS;TRANSID_MVOLA;STATE;MSISDN;PIVOT;SENS;NOM;TRANSID_PARENT;'
    'TRANS_TYPE;AMOUNT;SOLDE_PIVOT_AVANT;SOLDE_PIVOT_APRES;ORIGFTID;TYPE_OPERATION'
)


def make_row(transid='6757009839', amount='299600'):
    return (
        f'07/09/2026 00:50:49;{transid};Completed;0342022995;0385344178;C;Test Client;0;'
        f'wallettobank;{amount};613951496;614251096;87c0be73-f852-4845-88fd-e5361675ff0f;WTB'
    )


def make_csv(filename, rows):
    content = '\n'.join([HEADER, *rows]) + '\n'
    return SimpleUploadedFile(filename, content.encode('utf-8'), content_type='text/csv')


class ImporterFichierMvolaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')

    def test_import_valide_insere_les_transactions(self):
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row()])
        import_obj = importer_fichier_mvola(fichier, self.user)

        self.assertEqual(import_obj.statut, ImportFichierMvola.Statut.SUCCES)
        self.assertEqual(import_obj.nb_lignes_lues, 1)
        self.assertEqual(import_obj.nb_lignes_inserees, 1)
        self.assertEqual(import_obj.nb_doublons, 0)
        self.assertEqual(TransactionMvola.objects.count(), 1)
        self.assertEqual(import_obj.date_fichier, date(2026, 9, 7))

    def test_nom_fichier_invalide_rejete(self):
        fichier = make_csv('rapport_du_jour.csv', [make_row()])
        with self.assertRaises(FichierMvolaInvalide):
            importer_fichier_mvola(fichier, self.user)
        self.assertEqual(TransactionMvola.objects.count(), 0)

    def test_entete_invalide_rejete(self):
        content = 'A;B;C\n1;2;3\n'
        fichier = SimpleUploadedFile('2026-09-07_reporting_PAMF.csv', content.encode('utf-8'))
        with self.assertRaises(FichierMvolaInvalide):
            importer_fichier_mvola(fichier, self.user)

    def test_doublon_dans_le_meme_fichier_ignore(self):
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(), make_row()])
        import_obj = importer_fichier_mvola(fichier, self.user)

        self.assertEqual(import_obj.nb_lignes_inserees, 1)
        self.assertEqual(import_obj.nb_erreurs, 1)
        self.assertEqual(TransactionMvola.objects.count(), 1)

    def test_reimport_transid_existant_compte_comme_doublon(self):
        fichier1 = make_csv('2026-09-07_reporting_PAMF.csv', [make_row()])
        importer_fichier_mvola(fichier1, self.user)

        fichier2 = make_csv('2026-09-07_reporting_PAMF.csv', [make_row()])
        import_obj2 = importer_fichier_mvola(fichier2, self.user)

        self.assertEqual(import_obj2.nb_lignes_inserees, 0)
        self.assertEqual(import_obj2.nb_doublons, 1)
        self.assertEqual(TransactionMvola.objects.count(), 1)

    def test_ligne_avec_montant_invalide_ignoree_mais_import_continue(self):
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [
            make_row(transid='111', amount='pas_un_nombre'),
            make_row(transid='222', amount='5000'),
        ])
        import_obj = importer_fichier_mvola(fichier, self.user)

        self.assertEqual(import_obj.nb_lignes_inserees, 1)
        self.assertEqual(import_obj.nb_erreurs, 1)
        self.assertTrue(TransactionMvola.objects.filter(transid_mvola='222').exists())
        self.assertFalse(TransactionMvola.objects.filter(transid_mvola='111').exists())


class ImporterTransactionsPamfTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_import_succes_insere_les_transactions(self, mock_fetch):
        mock_fetch.return_value = [{
            'rAutotransactionID': 42,
            'postingDate': date(2026, 9, 7),
            'Time': '00:50:49',
            'Note': 'note',
            'TRANSID_MVOLA': '6757009839',
            'responseBody': '{"status": "ok"}',
        }]

        import_obj = importer_transactions_pamf(date(2026, 9, 7), self.user)

        self.assertEqual(import_obj.statut, ImportRequetePamf.Statut.SUCCES)
        self.assertEqual(import_obj.nb_lignes, 1)
        self.assertEqual(import_obj.nb_doublons, 0)
        self.assertEqual(TransactionPamf.objects.count(), 1)
        self.assertEqual(TransactionPamf.objects.first().transid_mvola, '6757009839')

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_transid_existant_compte_comme_doublon(self, mock_fetch):
        mock_fetch.return_value = [{
            'rAutotransactionID': 42,
            'postingDate': date(2026, 9, 7),
            'Time': '00:50:49',
            'Note': '',
            'TRANSID_MVOLA': '6757009839',
            'responseBody': '',
        }]
        importer_transactions_pamf(date(2026, 9, 7), self.user)
        import_obj2 = importer_transactions_pamf(date(2026, 9, 7), self.user)

        self.assertEqual(import_obj2.nb_lignes, 1)
        self.assertEqual(import_obj2.nb_doublons, 1)
        self.assertEqual(TransactionPamf.objects.count(), 1)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_erreur_connexion_marque_import_en_echec(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError('connexion refusee')

        import_obj = importer_transactions_pamf(date(2026, 9, 7), self.user)

        self.assertEqual(import_obj.statut, ImportRequetePamf.Statut.ECHEC)
        self.assertIn('connexion refusee', import_obj.message_erreur)
        self.assertEqual(TransactionPamf.objects.count(), 0)
