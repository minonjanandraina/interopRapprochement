import os
from datetime import date, datetime, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext

from .csv_mvola import FichierMvolaInvalide, importer_fichier_mvola
from .models import (
    ImportFichierMvola,
    ImportRequetePamf,
    Rapprochement,
    ResultatRapprochement,
    TransactionMvola,
    TransactionPamf,
)
from .forms import RapprochementForm
from .services_pamf import importer_transactions_pamf
from .services_rapprochement import CsvMvolaNonImporte, JourneeCbsNonTerminee, lancer_rapprochement

User = get_user_model()


def grant_privilege(user, code):
    from user.models import Permission, Role

    permission = Permission.objects.get(code=code)
    role = Role.objects.create(name=f'role-{code}-{user.pk}')
    role.permissions.add(permission)
    user.roles.add(role)

HEADER = (
    'DATE_TRANS;TRANSID_MVOLA;STATE;MSISDN;PIVOT;SENS;NOM;TRANSID_PARENT;'
    'TRANS_TYPE;AMOUNT;SOLDE_PIVOT_AVANT;SOLDE_PIVOT_APRES;ORIGFTID;TYPE_OPERATION'
)


def make_row(transid='6757009839', amount='299600', msisdn='0342022995', nom='Test Client',
             date_trans='07/09/2026 00:50:49', type_operation='WTB'):
    return (
        f'{date_trans};{transid};Completed;{msisdn};0385344178;C;{nom};0;'
        f'wallettobank;{amount};613951496;614251096;87c0be73-f852-4845-88fd-e5361675ff0f;{type_operation}'
    )


def make_csv(filename, rows):
    content = '\n'.join([HEADER, *rows]) + '\n'
    return SimpleUploadedFile(filename, content.encode('utf-8'), content_type='text/csv')


def journee_cbs_terminee(date_cible):
    """Horodatage de derniere activite CBS qui satisfait le critere de journee terminee
    (cf. JourneeCbsNonTerminee) pour `date_cible`, a utiliser comme mock par defaut dans les
    tests qui ne portent pas specifiquement sur ce controle."""
    return datetime.combine(date_cible, time(23, 0, 1))


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
    def test_ligne_apilog_sans_mctransaction_est_en_echec_sans_bloquer_limport(self, mock_fetch):
        """Une ligne apiLog sans correspondance dans mcTransaction (left join, cf. CLAUDE.md) a
        rAutotransactionID/Time a NULL : la requete a quand meme atteint le CBS, is_sucess=0."""
        mock_fetch.return_value = [{
            'rAutotransactionID': None,
            'postingDate': date(2026, 9, 7),
            'Time': None,
            'Note': None,
            'TRANSID_MVOLA': '6757009839',
            'responseBody': '',
            'is_sucess': 0,
        }]

        import_obj = importer_transactions_pamf(date(2026, 9, 7), self.user)

        self.assertEqual(import_obj.statut, ImportRequetePamf.Statut.SUCCES)
        transaction_pamf = TransactionPamf.objects.get(transid_mvola='6757009839')
        self.assertEqual(transaction_pamf.r_autotransaction_id, '')
        self.assertEqual(transaction_pamf.time, '')
        self.assertFalse(transaction_pamf.is_success)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_erreur_connexion_marque_import_en_echec(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError('connexion refusee')

        import_obj = importer_transactions_pamf(date(2026, 9, 7), self.user)

        self.assertEqual(import_obj.statut, ImportRequetePamf.Statut.ECHEC)
        self.assertIn('connexion refusee', import_obj.message_erreur)
        self.assertEqual(TransactionPamf.objects.count(), 0)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_paiement_scinde_sur_plusieurs_postings_est_accepte(self, mock_fetch):
        """cf. CLAUDE.md - decision du 2026-09-15 : un meme TRANSID_MVOLA (paiement marchand
        scinde sur plusieurs prets) peut avoir plusieurs postings CBS (rAutotransactionID
        distincts). Ne doit plus lever IntegrityError."""
        mock_fetch.return_value = [
            {'rAutotransactionID': 572435664, 'postingDate': date(2026, 9, 11), 'Time': '13:50:28',
             'Note': 'pret 1', 'TRANSID_MVOLA': 'MP260911.1350.D49614', 'responseBody': '{}', 'is_sucess': 1},
            {'rAutotransactionID': 572435666, 'postingDate': date(2026, 9, 11), 'Time': '13:50:28',
             'Note': 'pret 2', 'TRANSID_MVOLA': 'MP260911.1350.D49614', 'responseBody': '{}', 'is_sucess': 1},
        ]

        import_obj = importer_transactions_pamf(date(2026, 9, 11), self.user)

        self.assertEqual(import_obj.statut, ImportRequetePamf.Statut.SUCCES)
        self.assertEqual(TransactionPamf.objects.filter(transid_mvola='MP260911.1350.D49614').count(), 2)


class LancerRapprochementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.date_cible = date(2026, 9, 7)
        self.patcher_derniere_activite = patch('transactions.services_rapprochement.fetch_derniere_activite')
        self.mock_derniere_activite = self.patcher_derniere_activite.start()
        self.mock_derniere_activite.return_value = journee_cbs_terminee(self.date_cible)
        self.addCleanup(self.patcher_derniere_activite.stop)

    def test_bloque_si_csv_mvola_non_importe(self):
        with self.assertRaises(CsvMvolaNonImporte):
            lancer_rapprochement(self.date_cible, self.user)
        self.assertEqual(Rapprochement.objects.count(), 0)

    def test_bloque_si_journee_cbs_non_terminee(self):
        """cf. CLAUDE.md : journee D consideree terminee ssi la derniere activite CBS connue
        (apiLog, tous marchands/dates confondus) est >= D 23:00:00."""
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111')])
        importer_fichier_mvola(fichier, self.user)
        self.mock_derniere_activite.return_value = datetime(2026, 9, 7, 3, 52, 14)

        with self.assertRaises(JourneeCbsNonTerminee):
            lancer_rapprochement(self.date_cible, self.user)
        self.assertEqual(Rapprochement.objects.count(), 0)

    def test_bloque_si_apilog_vide(self):
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111')])
        importer_fichier_mvola(fichier, self.user)
        self.mock_derniere_activite.return_value = None

        with self.assertRaises(JourneeCbsNonTerminee):
            lancer_rapprochement(self.date_cible, self.user)
        self.assertEqual(Rapprochement.objects.count(), 0)

    def test_bloque_si_verification_journee_cbs_echoue(self):
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111')])
        importer_fichier_mvola(fichier, self.user)
        self.mock_derniere_activite.side_effect = RuntimeError('connexion refusee')

        with self.assertRaises(JourneeCbsNonTerminee):
            lancer_rapprochement(self.date_cible, self.user)
        self.assertEqual(Rapprochement.objects.count(), 0)

    def test_autorise_pile_a_lheure_limite(self):
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111')])
        importer_fichier_mvola(fichier, self.user)
        self.mock_derniere_activite.return_value = datetime(2026, 9, 7, 23, 0, 0)

        with patch('transactions.services_pamf.fetch_transactions_pamf') as mock_fetch:
            mock_fetch.return_value = []
            rapprochement = lancer_rapprochement(self.date_cible, self.user)

        self.assertEqual(rapprochement.statut, Rapprochement.Statut.TERMINE)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_classe_success_et_orphelines_et_genere_les_ecarts(self, mock_fetch):
        from ecarts.models import Ecart

        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111'), make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_MVOLA': '111', 'responseBody': ''},
            {'rAutotransactionID': 2, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_MVOLA': '999', 'responseBody': ''},
        ]

        rapprochement = lancer_rapprochement(self.date_cible, self.user)

        self.assertEqual(rapprochement.statut, Rapprochement.Statut.TERMINE)
        self.assertEqual(rapprochement.nb_mvola, 2)
        self.assertEqual(rapprochement.nb_pamf, 2)
        self.assertEqual(rapprochement.nb_success, 1)
        self.assertEqual(rapprochement.nb_orphelines_mvola, 1)
        self.assertEqual(rapprochement.nb_orphelines_pamf, 1)

        self.assertEqual(
            rapprochement.resultats.get(transid_mvola='111').statut, ResultatRapprochement.Statut.SUCCESS
        )
        self.assertEqual(
            rapprochement.resultats.get(transid_mvola='222').statut, ResultatRapprochement.Statut.ORPHELINE_MVOLA
        )
        self.assertEqual(
            rapprochement.resultats.get(transid_mvola='999').statut, ResultatRapprochement.Statut.ORPHELINE_PAMF
        )

        self.assertFalse(Ecart.objects.filter(transid_mvola='111').exists())
        self.assertTrue(Ecart.objects.filter(transid_mvola='222').exists())
        self.assertTrue(Ecart.objects.filter(transid_mvola='999').exists())

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_plusieurs_postings_pamf_sont_classes_doublon_pamf(self, mock_fetch):
        """cf. CLAUDE.md (decision du 2026-09-15) : un TRANSID_MVOLA avec plusieurs postings CBS
        (paiement scinde) n'est plus resolu automatiquement - statut DOUBLON_PAMF, transaction_pamf
        laisse a NULL, action recommandee CHOISIR_POSTING tant qu'aucun posting n'a ete choisi."""
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='SPLIT')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': 'pret 1', 'TRANSID_MVOLA': 'SPLIT', 'responseBody': '', 'is_sucess': 1},
            {'rAutotransactionID': 2, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': 'pret 2', 'TRANSID_MVOLA': 'SPLIT', 'responseBody': '', 'is_sucess': 1},
        ]

        rapprochement = lancer_rapprochement(self.date_cible, self.user)

        self.assertEqual(rapprochement.nb_doublons_pamf, 1)
        resultat = rapprochement.resultats.get(transid_mvola='SPLIT')
        self.assertEqual(resultat.statut, ResultatRapprochement.Statut.DOUBLON_PAMF)
        self.assertIsNone(resultat.transaction_pamf)
        self.assertEqual(resultat.action_recommandee, ResultatRapprochement.ActionRecommandee.CHOISIR_POSTING)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_absente_mvola_et_en_echec_pamf_est_exclue_du_resultat(self, mock_fetch):
        """cf. CLAUDE.md (decision du 2026-09-14) : absente cote MVOLA ET en echec cote PAMF ->
        aucun mouvement d'argent des deux cotes -> pas un ecart, exclue completement (pas de
        ResultatRapprochement ORPHELINE_PAMF, pas d'Ecart), contrairement a une ligne PAMF
        absente-mais-reussie qui reste une vraie orpheline PAMF a investiguer."""
        from ecarts.models import Ecart

        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_MVOLA': '111', 'responseBody': '', 'is_sucess': 1},
            {'rAutotransactionID': 2, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_MVOLA': '888', 'responseBody': '', 'is_sucess': 0},
            {'rAutotransactionID': 3, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_MVOLA': '999', 'responseBody': '', 'is_sucess': 1},
        ]

        rapprochement = lancer_rapprochement(self.date_cible, self.user)

        self.assertEqual(rapprochement.nb_success, 1)
        self.assertEqual(rapprochement.nb_orphelines_pamf, 1)
        self.assertFalse(ResultatRapprochement.objects.filter(transid_mvola='888').exists())
        self.assertTrue(ResultatRapprochement.objects.filter(transid_mvola='999').exists())
        self.assertFalse(Ecart.objects.filter(transid_mvola='888').exists())
        self.assertTrue(Ecart.objects.filter(transid_mvola='999').exists())

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_ligne_pamf_en_echec_est_orpheline_mvola_avec_action_ticket_aspekt(self, mock_fetch):
        """cf. nouvelle requete CBS : is_sucess=0 -> pas un vrai SUCCESS ; la requete a atteint
        Aspekt (une ligne PAMF existe) donc Aspekt peut corriger -> ticket recommande."""
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111'), make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_MVOLA': '111', 'responseBody': '', 'is_sucess': 1},
            {'rAutotransactionID': 2, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_MVOLA': '222', 'responseBody': '', 'is_sucess': 0},
        ]

        rapprochement = lancer_rapprochement(self.date_cible, self.user)

        self.assertEqual(rapprochement.nb_success, 1)
        self.assertEqual(rapprochement.nb_orphelines_mvola, 1)

        resultat_111 = rapprochement.resultats.get(transid_mvola='111')
        self.assertEqual(resultat_111.statut, ResultatRapprochement.Statut.SUCCESS)
        self.assertIsNone(resultat_111.action_recommandee)

        resultat_222 = rapprochement.resultats.get(transid_mvola='222')
        self.assertEqual(resultat_222.statut, ResultatRapprochement.Statut.ORPHELINE_MVOLA)
        self.assertFalse(resultat_222.transaction_pamf.is_success)
        self.assertEqual(resultat_222.action_recommandee, ResultatRapprochement.ActionRecommandee.TICKET_ASPEKT)

    def test_action_recommandee_rollback_si_aucune_ligne_pamf(self):
        """Aucune ligne PAMF -> la requete n'a pas atteint Aspekt -> rien a corriger la-bas -> rollback MVOLA."""
        rapprochement = Rapprochement.objects.create(date=self.date_cible)
        resultat = ResultatRapprochement.objects.create(
            rapprochement=rapprochement, transid_mvola='333',
            statut=ResultatRapprochement.Statut.ORPHELINE_MVOLA, transaction_pamf=None,
        )
        self.assertEqual(resultat.action_recommandee, ResultatRapprochement.ActionRecommandee.ROLLBACK_MVOLA)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_ligne_apilog_sans_mctransaction_recommande_ticket_aspekt(self, mock_fetch):
        """cf. CLAUDE.md (decision du 2026-09-14) : une trace apiLog sans mcTransaction associe
        prouve que le CBS a recu la requete -> ticket Aspekt, pas rollback MVOLA."""
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = [{
            'rAutotransactionID': None,
            'postingDate': self.date_cible,
            'Time': None,
            'Note': None,
            'TRANSID_MVOLA': '111',
            'responseBody': '',
            'is_sucess': 0,
        }]

        rapprochement = lancer_rapprochement(self.date_cible, self.user)

        resultat = rapprochement.resultats.get(transid_mvola='111')
        self.assertEqual(resultat.statut, ResultatRapprochement.Statut.ORPHELINE_MVOLA)
        self.assertFalse(resultat.transaction_pamf.is_success)
        self.assertEqual(resultat.action_recommandee, ResultatRapprochement.ActionRecommandee.TICKET_ASPEKT)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_detecete_transaction_rejouee_comme_orpheline_pamf_anterieure(self, mock_fetch):
        """Une orpheline PAMF qui correspond a une orpheline MVOLA d'une date anterieure est
        marquee comme TRANSACTION_REJOUEE, et le compteur est incremente."""
        from ecarts.models import Ecart

        # Premier rapprochement : orpheline MVOLA le 07/09
        fichier1 = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='REJOUEE')])
        importer_fichier_mvola(fichier1, self.user)
        mock_fetch.return_value = []

        rapprochement_1 = lancer_rapprochement(self.date_cible, self.user)
        self.assertEqual(rapprochement_1.nb_orphelines_mvola, 1)
        self.assertEqual(rapprochement_1.nb_transactions_rejouees, 0)

        resultat_1 = rapprochement_1.resultats.get(transid_mvola='REJOUEE')
        self.assertEqual(resultat_1.statut, ResultatRapprochement.Statut.ORPHELINE_MVOLA)

        # Deuxieme rapprochement : la meme transaction rejoueee apparait cote PAMF le 08/09
        date_cible_2 = date(2026, 9, 8)
        self.mock_derniere_activite.return_value = journee_cbs_terminee(date_cible_2)
        fichier2 = make_csv('2026-09-08_reporting_PAMF.csv', [make_row(transid='REJOUEE', date_trans='08/09/2026 12:00:00')])
        importer_fichier_mvola(fichier2, self.user)
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': date_cible_2, 'Time': '12:00:00',
             'Note': '', 'TRANSID_MVOLA': 'REJOUEE', 'responseBody': '', 'is_sucess': 1},
        ]

        rapprochement_2 = lancer_rapprochement(date_cible_2, self.user)
        self.assertEqual(rapprochement_2.nb_transactions_rejouees, 1)
        self.assertEqual(rapprochement_2.nb_orphelines_pamf, 0)

        resultat_2 = rapprochement_2.resultats.get(transid_mvola='REJOUEE')
        self.assertEqual(resultat_2.statut, ResultatRapprochement.Statut.TRANSACTION_REJOUEE)

        # Un ecart est genere pour la transaction rejouee
        self.assertTrue(Ecart.objects.filter(transid_mvola='REJOUEE', date_transaction=date_cible_2).exists())

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_echec_cbs_marque_le_rapprochement_en_echec(self, mock_fetch):
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.side_effect = RuntimeError('connexion refusee')

        rapprochement = lancer_rapprochement(self.date_cible, self.user)

        self.assertEqual(rapprochement.statut, Rapprochement.Statut.ECHEC)
        self.assertIn('connexion refusee', rapprochement.message_erreur)
        self.assertEqual(rapprochement.resultats.count(), 0)


class NotificationNouveauxEcartsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='op', email='op@example.com', password='x', is_email_verified=True,
        )
        self.date_cible = date(2026, 9, 7)
        self.patcher_derniere_activite = patch('transactions.services_rapprochement.fetch_derniere_activite')
        self.mock_derniere_activite = self.patcher_derniere_activite.start()
        self.mock_derniere_activite.return_value = journee_cbs_terminee(self.date_cible)
        self.addCleanup(self.patcher_derniere_activite.stop)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_notifie_les_utilisateurs_verifies_si_nouveaux_ecarts(self, mock_fetch):
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = []

        with self.captureOnCommitCallbacks(execute=True):
            lancer_rapprochement(self.date_cible, self.user)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)
        self.assertIn('222', mail.outbox[0].body)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_relance_renotifie_car_les_ecarts_sont_recrees(self, mock_fetch):
        """Une relance efface et recree les Ecart (cf. Decisions prises) : le systeme ne peut
        donc plus distinguer un ecart deja connu d'un ecart reellement nouveau, et renotifie a
        chaque relance tant que l'ecart existe."""
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = []

        with self.captureOnCommitCallbacks(execute=True):
            lancer_rapprochement(self.date_cible, self.user)
        with self.captureOnCommitCallbacks(execute=True):
            lancer_rapprochement(self.date_cible, self.user)

        self.assertEqual(len(mail.outbox), 2)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_aucun_destinataire_verifie_alors_pas_denvoi(self, mock_fetch):
        self.user.is_email_verified = False
        self.user.save()
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = []

        with self.captureOnCommitCallbacks(execute=True):
            lancer_rapprochement(self.date_cible, self.user)

        self.assertEqual(len(mail.outbox), 0)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_notifie_les_comptes_staff_meme_sans_email_verifie(self, mock_fetch):
        admin = User.objects.create_user(
            username='admin', email='admin@example.com', password='x',
            is_staff=True, is_email_verified=False,
        )
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='333')])
        importer_fichier_mvola(fichier, admin)
        mock_fetch.return_value = []

        with self.captureOnCommitCallbacks(execute=True):
            lancer_rapprochement(self.date_cible, admin)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('admin@example.com', mail.outbox[0].to)

    @patch('ecarts.notifications.send_mail')
    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_echec_envoi_ne_bloque_pas_le_rapprochement(self, mock_fetch, mock_send_mail):
        mock_send_mail.side_effect = RuntimeError('smtp indisponible')
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = []

        with self.captureOnCommitCallbacks(execute=True):
            rapprochement = lancer_rapprochement(self.date_cible, self.user)

        self.assertEqual(rapprochement.statut, Rapprochement.Statut.TERMINE)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_relance_efface_le_traitement_deja_effectue(self, mock_fetch):
        """Decision produit : relancer une date deja traitee efface et recalcule tout, y compris
        le travail de regularisation deja fait (cf. services_rapprochement docstring)."""
        from ecarts.models import Ecart, EcartHistorique

        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = []

        rapprochement = lancer_rapprochement(self.date_cible, self.user)
        ecart = Ecart.objects.get(transid_mvola='222')
        ecart.statut = Ecart.Statut.REGULARISE
        ecart.save()
        EcartHistorique.objects.create(
            ecart=ecart, auteur=self.user, action=EcartHistorique.Action.COMMENTAIRE, commentaire='traite',
        )
        ancien_resultat_pk = rapprochement.resultats.get(transid_mvola='222').pk
        ancien_ecart_pk = ecart.pk

        lancer_rapprochement(self.date_cible, self.user)

        self.assertFalse(ResultatRapprochement.objects.filter(pk=ancien_resultat_pk).exists())
        self.assertFalse(Ecart.objects.filter(pk=ancien_ecart_pk).exists())
        self.assertFalse(EcartHistorique.objects.filter(ecart_id=ancien_ecart_pk).exists())

        nouvel_ecart = Ecart.objects.get(transid_mvola='222')
        self.assertEqual(nouvel_ecart.statut, Ecart.Statut.DETECTE)
        self.assertNotEqual(nouvel_ecart.pk, ancien_ecart_pk)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_relance_supprime_la_piece_jointe_physique(self, mock_fetch):
        from ecarts.models import Ecart
        from ecarts.services import ajouter_piece_jointe

        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = []

        lancer_rapprochement(self.date_cible, self.user)
        ecart = Ecart.objects.get(transid_mvola='222')
        piece = SimpleUploadedFile('preuve.txt', b'contenu', content_type='text/plain')
        entree = ajouter_piece_jointe(ecart, self.user, piece)
        chemin_fichier = entree.fichier.path
        self.assertTrue(os.path.exists(chemin_fichier))

        lancer_rapprochement(self.date_cible, self.user)

        self.assertFalse(os.path.exists(chemin_fichier))


class LancerRapprochementPerformanceTests(TestCase):
    """Le matching doit rester en nombre de requetes borne, pas O(n) sur le volume du jour."""

    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.date_cible = date(2026, 9, 7)
        self.patcher_derniere_activite = patch('transactions.services_rapprochement.fetch_derniere_activite')
        self.mock_derniere_activite = self.patcher_derniere_activite.start()
        self.mock_derniere_activite.return_value = journee_cbs_terminee(self.date_cible)
        self.addCleanup(self.patcher_derniere_activite.stop)

    def _nb_requetes_pour_une_relance(self, nb_transactions):
        rows = [make_row(transid=f'T{i}') for i in range(nb_transactions)]
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', rows)
        importer_fichier_mvola(fichier, self.user)

        with patch('transactions.services_pamf.fetch_transactions_pamf') as mock_fetch:
            mock_fetch.return_value = [
                {'rAutotransactionID': i, 'postingDate': self.date_cible, 'Time': '00:00:00',
                 'Note': '', 'TRANSID_MVOLA': f'T{i}', 'responseBody': ''}
                for i in range(nb_transactions)
            ]
            lancer_rapprochement(self.date_cible, self.user)
            with CaptureQueriesContext(connection) as ctx:
                lancer_rapprochement(self.date_cible, self.user)

        Rapprochement.objects.all().delete()
        TransactionMvola.objects.all().delete()
        TransactionPamf.objects.all().delete()
        ImportFichierMvola.objects.all().delete()
        ImportRequetePamf.objects.all().delete()
        return len(ctx.captured_queries)

    def test_nombre_de_requetes_ne_scale_pas_avec_le_volume(self):
        nb_requetes_10 = self._nb_requetes_pour_une_relance(10)
        nb_requetes_100 = self._nb_requetes_pour_une_relance(100)

        self.assertLess(nb_requetes_100, nb_requetes_10 + 10)


class ListeMvolaViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [
            make_row(transid='111', msisdn='0341111111', nom='Alice', type_operation='WTB'),
            make_row(transid='222', msisdn='0342222222', nom='Bob', type_operation='BTW'),
        ])
        importer_fichier_mvola(fichier, self.user)

    def test_affiche_toutes_les_transactions_sans_filtre(self):
        resp = self.client.get('/transactions/mvola/transactions/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '111')
        self.assertContains(resp, '222')

    def test_filtre_par_msisdn(self):
        resp = self.client.get('/transactions/mvola/transactions/', {'msisdn': '0341111111'})
        self.assertContains(resp, '111')
        self.assertNotContains(resp, '222')

    def test_filtre_par_type_operation(self):
        resp = self.client.get('/transactions/mvola/transactions/', {'type_operation': 'BTW'})
        self.assertContains(resp, '222')
        self.assertNotContains(resp, '111')

    def test_requete_htmx_ne_renvoie_que_le_fragment(self):
        resp = self.client.get('/transactions/mvola/transactions/', HTTP_HX_REQUEST='true')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, '<title>')
        self.assertContains(resp, '111')


class ListePamfViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_affiche_les_transactions_et_filtre_par_transid(self, mock_fetch):
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
             'Note': '', 'TRANSID_MVOLA': '111', 'responseBody': ''},
            {'rAutotransactionID': 2, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
             'Note': '', 'TRANSID_MVOLA': '222', 'responseBody': ''},
        ]
        importer_transactions_pamf(date(2026, 9, 7), self.user)

        resp = self.client.get('/transactions/mvola/pamf/')
        self.assertContains(resp, '111')
        self.assertContains(resp, '222')

        resp2 = self.client.get('/transactions/mvola/pamf/', {'transid_mvola': '111'})
        self.assertContains(resp2, '111')
        self.assertNotContains(resp2, '222')


class ExportListesTests(TestCase):
    """Export Excel/PDF des 3 listes de consultation : respecte les filtres, toutes les lignes."""

    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [
            make_row(transid='111', msisdn='0341111111', nom='Alice', type_operation='WTB'),
            make_row(transid='222', msisdn='0342222222', nom='Bob', type_operation='BTW'),
        ])
        importer_fichier_mvola(fichier, self.user)
        with patch('transactions.services_pamf.fetch_transactions_pamf') as mock_fetch:
            mock_fetch.return_value = [
                {'rAutotransactionID': 1, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': '', 'TRANSID_MVOLA': '111', 'responseBody': ''},
            ]
            importer_transactions_pamf(date(2026, 9, 7), self.user)

    def test_export_excel_mvola_respecte_le_filtre(self):
        resp = self.client.get('/transactions/mvola/transactions/export/excel/', {'msisdn': '0341111111'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('transactions_mvola.xlsx', resp['Content-Disposition'])

    def test_export_pdf_mvola_respecte_le_filtre(self):
        resp = self.client.get('/transactions/mvola/transactions/export/pdf/', {'msisdn': '0341111111'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('transactions_mvola.pdf', resp['Content-Disposition'])

    def test_export_excel_pamf(self):
        resp = self.client.get('/transactions/mvola/pamf/export/excel/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('transactions_pamf.xlsx', resp['Content-Disposition'])

    def test_export_pdf_pamf(self):
        resp = self.client.get('/transactions/mvola/pamf/export/pdf/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('transactions_pamf.pdf', resp['Content-Disposition'])

    def test_format_export_inconnu_renvoie_404(self):
        resp = self.client.get('/transactions/mvola/transactions/export/csv/')
        self.assertEqual(resp.status_code, 404)

    def test_entete_de_rapport_affiche_les_filtres_et_le_total(self):
        resp = self.client.get('/transactions/mvola/transactions/', {'msisdn': '0341111111'})
        self.assertContains(resp, 'MSISDN = 0341111111')
        self.assertContains(resp, '1 ligne')
        self.assertContains(resp, 'op')


class RapprochementLignesViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111'), make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        with patch('transactions.services_pamf.fetch_transactions_pamf') as mock_fetch, \
                patch('transactions.services_rapprochement.fetch_derniere_activite') as mock_derniere_activite:
            mock_fetch.return_value = [
                {'rAutotransactionID': 1, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': '', 'TRANSID_MVOLA': '111', 'responseBody': ''},
            ]
            mock_derniere_activite.return_value = journee_cbs_terminee(date(2026, 9, 7))
            self.rapprochement = lancer_rapprochement(date(2026, 9, 7), self.user)

    def test_lignes_mvola_affiche_lentete_et_le_tableau(self):
        resp = self.client.get(
            f'/transactions/mvola/rapprochement/{self.rapprochement.pk}/lignes/mvola/',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '111')
        self.assertContains(resp, '222')

    def test_export_excel_orphelines(self):
        resp = self.client.get(
            f'/transactions/mvola/rapprochement/{self.rapprochement.pk}/lignes/orphelines/export/excel/',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            f'rapprochement_{self.rapprochement.date.isoformat()}_orphelines.xlsx', resp['Content-Disposition'],
        )

    def test_export_pdf_pamf_du_rapprochement(self):
        resp = self.client.get(
            f'/transactions/mvola/rapprochement/{self.rapprochement.pk}/lignes/pamf/export/pdf/',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')


class RapprochementFormTests(TestCase):
    def test_plage_valide(self):
        form = RapprochementForm(data={'date_from': '2026-09-07', 'date_to': '2026-09-09'})
        self.assertTrue(form.is_valid())

    def test_date_from_apres_date_to_rejetee(self):
        form = RapprochementForm(data={'date_from': '2026-09-09', 'date_to': '2026-09-07'})
        self.assertFalse(form.is_valid())

    def test_plage_trop_longue_rejetee(self):
        form = RapprochementForm(data={'date_from': '2026-01-01', 'date_to': '2026-03-01'})
        self.assertFalse(form.is_valid())


class MvolaRapprochementLancerDateViewTests(TestCase):
    """Endpoint AJAX appele par le navigateur, une date a la fois, pour piloter le modal de
    progression sur une plage (cf. rapprochement_mvola.html)."""

    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        grant_privilege(self.user, 'lancer_rapprochement')
        self.client = Client()
        self.client.force_login(self.user)
        self.patcher_derniere_activite = patch('transactions.services_rapprochement.fetch_derniere_activite')
        self.mock_derniere_activite = self.patcher_derniere_activite.start()
        self.mock_derniere_activite.return_value = journee_cbs_terminee(date(2026, 9, 7))
        self.addCleanup(self.patcher_derniere_activite.stop)

    def test_date_invalide_retourne_400(self):
        resp = self.client.post('/transactions/mvola/rapprochement/lancer-date/', {'date': 'pas-une-date'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['ok'])

    def test_csv_non_importe_retourne_ok_false(self):
        resp = self.client.post('/transactions/mvola/rapprochement/lancer-date/', {'date': '2026-09-07'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['ok'])
        self.assertIn('pas encore ete importe', data['message'])
        self.assertEqual(Rapprochement.objects.count(), 0)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_succes_retourne_ok_true(self, mock_fetch):
        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111')])
        importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = []

        resp = self.client.post('/transactions/mvola/rapprochement/lancer-date/', {'date': '2026-09-07'})

        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['date'], '2026-09-07')
        self.assertEqual(Rapprochement.objects.get(date=date(2026, 9, 7)).statut, Rapprochement.Statut.TERMINE)

    def test_sans_privilege_refuse(self):
        autre_user = User.objects.create_user(username='sans-droit', email='sd@example.com', password='x')
        self.client.force_login(autre_user)

        resp = self.client.post('/transactions/mvola/rapprochement/lancer-date/', {'date': '2026-09-07'})

        self.assertEqual(resp.status_code, 403)


class MvolaRapprochementPlageViewTests(TestCase):
    """Fallback sans JS : soumission classique du formulaire, traite toute la plage d'un coup."""

    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        grant_privilege(self.user, 'lancer_rapprochement')
        self.client = Client()
        self.client.force_login(self.user)
        self.patcher_derniere_activite = patch('transactions.services_rapprochement.fetch_derniere_activite')
        self.mock_derniere_activite = self.patcher_derniere_activite.start()
        self.mock_derniere_activite.return_value = journee_cbs_terminee(date(2026, 9, 9))
        self.addCleanup(self.patcher_derniere_activite.stop)

    @patch('transactions.services_pamf.fetch_transactions_pamf')
    def test_lance_un_rapprochement_par_date_de_la_plage(self, mock_fetch):
        for jour in ('07', '08', '09'):
            fichier = make_csv(f'2026-09-{jour}_reporting_PAMF.csv', [make_row(transid=f't{jour}')])
            importer_fichier_mvola(fichier, self.user)
        mock_fetch.return_value = []

        resp = self.client.post('/transactions/mvola/rapprochement/', {
            'date_from': '2026-09-07', 'date_to': '2026-09-09',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Rapprochement.objects.count(), 3)
        self.assertTrue(Rapprochement.objects.filter(date=date(2026, 9, 7)).exists())
        self.assertTrue(Rapprochement.objects.filter(date=date(2026, 9, 8)).exists())
        self.assertTrue(Rapprochement.objects.filter(date=date(2026, 9, 9)).exists())
