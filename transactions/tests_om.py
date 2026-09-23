"""Tests Orange Money (OM) - miroir cible des points a risque de tests.py (MVOLA), pas une copie
ligne a ligne : cf. CLAUDE.md, Decisions prises (duplication OM)."""

import os
from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from .forms import ImportOMForm
from .models import (
    ImportFichierOM,
    ImportRequeteOM,
    RapprochementOM,
    ResultatRapprochementOM,
    TransactionOM,
    TransactionPamfOM,
)
from .services_pamf_om import importer_transactions_pamf_om
from .services_rapprochement_om import FichierOMNonImporte, lancer_rapprochement_om
from .xls_om import FichierOMInvalide, extraire_date_du_nom, importer_fichier_om
from .tests import grant_privilege

User = get_user_model()

FICHIER_REEL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'input', 'Daily-ChannelUserTransactionReport-0324660679-20260907.xls',
)


def journee_cbs_terminee(date_cible):
    return datetime.combine(date_cible, time(23, 0, 1))


def lire_fichier_reel(nom=None):
    with open(FICHIER_REEL, 'rb') as f:
        contenu = f.read()
    return SimpleUploadedFile(
        nom or os.path.basename(FICHIER_REEL), contenu,
        content_type='application/vnd.ms-excel',
    )


def make_import_om(user, date_fichier=date(2026, 9, 7)):
    return ImportFichierOM.objects.create(
        fichier=SimpleUploadedFile('fake.xls', b'x'),
        nom_original=f'Daily-ChannelUserTransactionReport-0324660679-{date_fichier.strftime("%Y%m%d")}.xls',
        date_fichier=date_fichier,
        importe_par=user,
        statut=ImportFichierOM.Statut.SUCCES,
    )


def make_transaction_om(import_obj, transid, msisdn='0340000000', montant='10000', date_trans=None):
    return TransactionOM.objects.create(
        numero_ligne=1,
        date_trans=date_trans or timezone.make_aware(datetime(2026, 9, 7, 10, 0, 0)),
        transid_om=transid,
        statut='Succès',
        msisdn=msisdn,
        montant=montant,
        import_fichier=import_obj,
    )


class ExtraireDateDuNomTests(TestCase):
    def test_date_extraite_du_nom(self):
        self.assertEqual(
            extraire_date_du_nom('Daily-ChannelUserTransactionReport-0324660679-20260907.xls'),
            date(2026, 9, 7),
        )

    def test_nom_invalide_leve_fichier_om_invalide(self):
        with self.assertRaises(FichierOMInvalide):
            extraire_date_du_nom('rapport_du_jour.xls')


class ImportOMFormTests(TestCase):
    def test_extension_xls_requise(self):
        fichier = SimpleUploadedFile('rapport.csv', b'x')
        form = ImportOMForm(data={}, files={'fichier': fichier})
        self.assertFalse(form.is_valid())
        self.assertIn('fichier', form.errors)


class ImporterFichierOMSurDonneesReellesTests(TestCase):
    """Utilise le vrai fichier de /input (cf. CLAUDE.md) pour valider le parsing XLS Orange
    Money sur des donnees reelles."""

    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')

    def test_import_ne_garde_que_les_lignes_succes(self):
        import_obj = importer_fichier_om(lire_fichier_reel(), self.user)

        self.assertEqual(import_obj.statut, ImportFichierOM.Statut.SUCCES)
        self.assertEqual(import_obj.date_fichier, date(2026, 9, 7))
        # Verifie sur le fichier reel : 190 lignes de donnees (31 Echec + 159 Succes).
        self.assertEqual(import_obj.nb_lignes_lues, 190)
        self.assertEqual(import_obj.nb_hors_succes, 31)
        self.assertEqual(import_obj.nb_lignes_inserees, 159)
        self.assertEqual(TransactionOM.objects.count(), 159)

    def test_valeurs_dune_ligne_connue(self):
        importer_fichier_om(lire_fichier_reel(), self.user)

        t = TransactionOM.objects.get(transid_om='MP260907.0629.B32073')
        self.assertEqual(t.msisdn, '0324044263')
        self.assertEqual(t.montant, 100000)
        self.assertEqual(t.statut, 'Succès')
        self.assertFalse(TransactionOM.objects.filter(transid_om='MP260907.1434.D68447').exists())

    def test_reimport_est_entierement_deduplique(self):
        importer_fichier_om(lire_fichier_reel(), self.user)
        import_obj2 = importer_fichier_om(lire_fichier_reel(), self.user)

        self.assertEqual(import_obj2.nb_lignes_inserees, 0)
        self.assertEqual(import_obj2.nb_doublons, 159)
        self.assertEqual(TransactionOM.objects.count(), 159)

    def test_fichier_illisible_leve_fichier_om_invalide(self):
        fichier = SimpleUploadedFile(
            'Daily-ChannelUserTransactionReport-0324660679-20260907.xls', b'pas un fichier xls',
        )
        with self.assertRaises(FichierOMInvalide):
            importer_fichier_om(fichier, self.user)
        self.assertEqual(TransactionOM.objects.count(), 0)


class ImporterTransactionsPamfOMTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_import_succes_insere_les_transactions(self, mock_fetch):
        mock_fetch.return_value = [{
            'rAutotransactionID': 42, 'postingDate': date(2026, 9, 7), 'Time': '00:50:49',
            'Note': 'note', 'TRANSID_ORANGE_MONEY': 'MP260907.0629.B32073', 'responseBody': '{"status": "ok"}',
        }]

        import_obj = importer_transactions_pamf_om(date(2026, 9, 7), self.user)

        self.assertEqual(import_obj.statut, ImportRequeteOM.Statut.SUCCES)
        self.assertEqual(TransactionPamfOM.objects.count(), 1)
        self.assertTrue(TransactionPamfOM.objects.get().is_success)

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_montant_de_la_ligne_cbs_est_stocke(self, mock_fetch):
        """cf. CLAUDE.md - decision du 2026-09-15 : REQUETE_PAMF_OM agrege desormais les
        remboursements scindes (apiServiceId=303) en une seule ligne avec la somme des postings
        (colonne Amount) - stockee dans TransactionPamfOM.montant."""
        mock_fetch.return_value = [{
            'rAutotransactionID': 572435664, 'postingDate': date(2026, 9, 8), 'Time': '13:50:28',
            'Note': '01150999-01-0459750-00160; 01150999-01-0459750-00163',
            'TRANSID_ORANGE_MONEY': 'MP260908.1350.D49614', 'responseBody': '{}',
            'apiServiceId': 303, 'Amount': Decimal('72200.00'), 'is_sucess': 1,
        }]

        importer_transactions_pamf_om(date(2026, 9, 8), self.user)

        self.assertEqual(TransactionPamfOM.objects.get().montant, Decimal('72200.00'))

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_erreur_connexion_marque_import_en_echec(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError('connexion refusee')

        import_obj = importer_transactions_pamf_om(date(2026, 9, 7), self.user)

        self.assertEqual(import_obj.statut, ImportRequeteOM.Statut.ECHEC)
        self.assertIn('connexion refusee', import_obj.message_erreur)
        self.assertEqual(TransactionPamfOM.objects.count(), 0)

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_paiement_scinde_sur_plusieurs_postings_est_accepte(self, mock_fetch):
        """cf. CLAUDE.md - decision du 2026-09-15 : un meme transid_om peut avoir plusieurs
        postings CBS (rAutotransactionID distincts) - ne doit plus lever IntegrityError (cf.
        incident reel du 08/09/2026). Le cas d'un remboursement scinde sur plusieurs prets
        (apiServiceId=303) est desormais deja agrege en une seule ligne par REQUETE_PAMF_OM ;
        ce test verifie le comportement de secours si plusieurs lignes arrivent quand meme
        (ex. apiServiceId 302/700, cf. principe DOUBLON_PAMF)."""
        mock_fetch.return_value = [
            {'rAutotransactionID': 572435664, 'postingDate': date(2026, 9, 8), 'Time': '13:50:28',
             'Note': 'pret 1', 'TRANSID_ORANGE_MONEY': 'MP260908.1350.D49614', 'responseBody': '{}', 'is_sucess': 1},
            {'rAutotransactionID': 572435666, 'postingDate': date(2026, 9, 8), 'Time': '13:50:28',
             'Note': 'pret 2', 'TRANSID_ORANGE_MONEY': 'MP260908.1350.D49614', 'responseBody': '{}', 'is_sucess': 1},
        ]

        import_obj = importer_transactions_pamf_om(date(2026, 9, 8), self.user)

        self.assertEqual(import_obj.statut, ImportRequeteOM.Statut.SUCCES)
        self.assertEqual(TransactionPamfOM.objects.filter(transid_om='MP260908.1350.D49614').count(), 2)

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_reimport_dun_paiement_scinde_est_deduplique_par_posting(self, mock_fetch):
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': date(2026, 9, 8), 'Time': '00:00:00',
             'Note': '', 'TRANSID_ORANGE_MONEY': 'X', 'responseBody': '', 'is_sucess': 1},
            {'rAutotransactionID': 2, 'postingDate': date(2026, 9, 8), 'Time': '00:00:00',
             'Note': '', 'TRANSID_ORANGE_MONEY': 'X', 'responseBody': '', 'is_sucess': 1},
        ]
        importer_transactions_pamf_om(date(2026, 9, 8), self.user)
        import_obj2 = importer_transactions_pamf_om(date(2026, 9, 8), self.user)

        self.assertEqual(import_obj2.nb_doublons, 2)
        self.assertEqual(TransactionPamfOM.objects.filter(transid_om='X').count(), 2)


class LancerRapprochementOMTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.date_cible = date(2026, 9, 7)
        self.patcher_derniere_activite = patch('transactions.services_rapprochement.fetch_derniere_activite')
        self.mock_derniere_activite = self.patcher_derniere_activite.start()
        self.mock_derniere_activite.return_value = journee_cbs_terminee(self.date_cible)
        self.addCleanup(self.patcher_derniere_activite.stop)

    def test_bloque_si_fichier_om_non_importe(self):
        with self.assertRaises(FichierOMNonImporte):
            lancer_rapprochement_om(self.date_cible, self.user)
        self.assertEqual(RapprochementOM.objects.count(), 0)

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_classe_success_et_orphelines_et_genere_les_ecarts(self, mock_fetch):
        from ecarts.models import EcartOM

        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, '111')
        make_transaction_om(import_obj, '222')
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_ORANGE_MONEY': '111', 'responseBody': ''},
            {'rAutotransactionID': 2, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_ORANGE_MONEY': '999', 'responseBody': ''},
        ]

        rapprochement = lancer_rapprochement_om(self.date_cible, self.user)

        self.assertEqual(rapprochement.statut, RapprochementOM.Statut.TERMINE)
        self.assertEqual(rapprochement.nb_om, 2)
        self.assertEqual(rapprochement.nb_pamf, 2)
        self.assertEqual(rapprochement.nb_success, 1)
        self.assertEqual(rapprochement.nb_orphelines_om, 1)
        self.assertEqual(rapprochement.nb_orphelines_pamf, 1)

        self.assertEqual(
            rapprochement.resultats.get(transid_om='111').statut, ResultatRapprochementOM.Statut.SUCCESS
        )
        self.assertEqual(
            rapprochement.resultats.get(transid_om='222').statut, ResultatRapprochementOM.Statut.ORPHELINE_OM
        )
        self.assertEqual(
            rapprochement.resultats.get(transid_om='999').statut, ResultatRapprochementOM.Statut.ORPHELINE_PAMF
        )

        self.assertFalse(EcartOM.objects.filter(transid_om='111').exists())
        self.assertTrue(EcartOM.objects.filter(transid_om='222').exists())
        self.assertTrue(EcartOM.objects.filter(transid_om='999').exists())

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_absente_om_et_en_echec_pamf_est_exclue_du_resultat(self, mock_fetch):
        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, '111')
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_ORANGE_MONEY': '111', 'responseBody': '', 'is_sucess': 1},
            {'rAutotransactionID': 2, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_ORANGE_MONEY': '888', 'responseBody': '', 'is_sucess': 0},
        ]

        rapprochement = lancer_rapprochement_om(self.date_cible, self.user)

        self.assertEqual(rapprochement.nb_success, 1)
        self.assertEqual(rapprochement.nb_orphelines_pamf, 0)
        self.assertFalse(ResultatRapprochementOM.objects.filter(transid_om='888').exists())

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_plusieurs_postings_pamf_sont_classes_doublon_pamf_meme_si_tous_reussissent(self, mock_fetch):
        """cf. CLAUDE.md - decision du 2026-09-15 (rollback de l'agregation automatique) : si le
        moteur recoit plusieurs lignes PAMF pour un meme transid_om (ex. apiServiceId 302/700 -
        le cas apiServiceId=303, remboursement scinde sur plusieurs prets, est deja agrege en
        amont par REQUETE_PAMF_OM), il ne resout plus automatiquement en SUCCESS - l'agent doit
        choisir le posting de reference, meme si tous les postings ont reussi."""
        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, 'SPLIT-OK')
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': 'pret 1', 'TRANSID_ORANGE_MONEY': 'SPLIT-OK', 'responseBody': '', 'is_sucess': 1},
            {'rAutotransactionID': 2, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': 'pret 2', 'TRANSID_ORANGE_MONEY': 'SPLIT-OK', 'responseBody': '', 'is_sucess': 1},
        ]

        rapprochement = lancer_rapprochement_om(self.date_cible, self.user)

        self.assertEqual(rapprochement.nb_pamf, 1)
        self.assertEqual(rapprochement.nb_doublons_pamf, 1)
        resultat = rapprochement.resultats.get(transid_om='SPLIT-OK')
        self.assertEqual(resultat.statut, ResultatRapprochementOM.Statut.DOUBLON_PAMF)
        self.assertIsNone(resultat.transaction_pamf)
        self.assertEqual(resultat.action_recommandee, ResultatRapprochementOM.ActionRecommandee.CHOISIR_POSTING)

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_plusieurs_postings_pamf_avec_un_echec_restent_classes_doublon_pamf(self, mock_fetch):
        """Meme quand un seul des postings echoue, le cas reste DOUBLON_PAMF (ambigu) - pas
        d'agregation automatique, cf. rollback de la decision precedente."""
        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, 'SPLIT-PARTIEL')
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': 'pret 1', 'TRANSID_ORANGE_MONEY': 'SPLIT-PARTIEL', 'responseBody': '', 'is_sucess': 1},
            {'rAutotransactionID': 2, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': 'pret 2', 'TRANSID_ORANGE_MONEY': 'SPLIT-PARTIEL', 'responseBody': '', 'is_sucess': 0},
        ]

        rapprochement = lancer_rapprochement_om(self.date_cible, self.user)

        resultat = rapprochement.resultats.get(transid_om='SPLIT-PARTIEL')
        self.assertEqual(resultat.statut, ResultatRapprochementOM.Statut.DOUBLON_PAMF)
        self.assertEqual(resultat.action_recommandee, ResultatRapprochementOM.ActionRecommandee.CHOISIR_POSTING)

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_action_recommandee_rollback_si_aucune_ligne_pamf(self, mock_fetch):
        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, '111')
        mock_fetch.return_value = []

        rapprochement = lancer_rapprochement_om(self.date_cible, self.user)

        resultat = rapprochement.resultats.get(transid_om='111')
        self.assertEqual(resultat.action_recommandee, ResultatRapprochementOM.ActionRecommandee.ROLLBACK_OM)

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_action_recommandee_ticket_aspekt_si_ligne_pamf_en_echec(self, mock_fetch):
        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, '111')
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': self.date_cible, 'Time': '00:00:00',
             'Note': '', 'TRANSID_ORANGE_MONEY': '111', 'responseBody': '', 'is_sucess': 0},
        ]

        rapprochement = lancer_rapprochement_om(self.date_cible, self.user)

        resultat = rapprochement.resultats.get(transid_om='111')
        self.assertEqual(resultat.action_recommandee, ResultatRapprochementOM.ActionRecommandee.TICKET_ASPEKT)

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_relance_purge_et_recalcule(self, mock_fetch):
        """Cf. CLAUDE.md - relance destructive assumee : le traitement deja effectue sur une
        date (ici un EcartOM detecte) ne survit pas a une relance de cette date."""
        from ecarts.models import EcartOM

        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, '111')
        mock_fetch.return_value = []

        rapprochement = lancer_rapprochement_om(self.date_cible, self.user)
        ecart_id_avant = EcartOM.objects.get(transid_om='111').pk

        rapprochement = lancer_rapprochement_om(self.date_cible, self.user)
        ecart_apres = EcartOM.objects.get(transid_om='111')

        self.assertNotEqual(ecart_id_avant, ecart_apres.pk)
        self.assertEqual(EcartOM.objects.filter(transid_om='111').count(), 1)

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_detecete_transaction_rejouee_comme_orpheline_pamf_anterieure(self, mock_fetch):
        """Une orpheline PAMF qui correspond a une orpheline OM d'une date anterieure est
        marquee comme TRANSACTION_REJOUEE avec statut REGULARISE, et le compteur est incremente."""
        from ecarts.models import EcartOM

        # Premier rapprochement : orpheline OM le 07/09
        import_obj_1 = make_import_om(self.user, date_fichier=self.date_cible)
        make_transaction_om(import_obj_1, 'REJOUEE')
        mock_fetch.return_value = []

        rapprochement_1 = lancer_rapprochement_om(self.date_cible, self.user)
        self.assertEqual(rapprochement_1.nb_orphelines_om, 1)
        self.assertEqual(rapprochement_1.nb_transactions_rejouees, 0)

        resultat_1 = rapprochement_1.resultats.get(transid_om='REJOUEE')
        self.assertEqual(resultat_1.statut, ResultatRapprochementOM.Statut.ORPHELINE_OM)

        # Deuxieme rapprochement : la meme transaction rejouee (pas reimportee cote OM, juste
        # absent du fichier OM du 08/09) apparait cote PAMF le 08/09 - statut TRANSACTION_REJOUEE
        date_cible_2 = date(2026, 9, 8)
        self.mock_derniere_activite.return_value = journee_cbs_terminee(date_cible_2)
        import_obj_2 = make_import_om(self.user, date_fichier=date_cible_2)
        make_transaction_om(import_obj_2, 'AUTRE')  # Une autre transaction OM pour cette date
        mock_fetch.return_value = [
            {'rAutotransactionID': 1, 'postingDate': date_cible_2, 'Time': '12:00:00',
             'Note': '', 'TRANSID_ORANGE_MONEY': 'REJOUEE', 'responseBody': '', 'is_sucess': 1},
        ]

        rapprochement_2 = lancer_rapprochement_om(date_cible_2, self.user)
        self.assertEqual(rapprochement_2.nb_transactions_rejouees, 1)
        self.assertEqual(rapprochement_2.nb_orphelines_pamf, 0)

        resultat_2 = rapprochement_2.resultats.get(transid_om='REJOUEE')
        self.assertEqual(resultat_2.statut, ResultatRapprochementOM.Statut.TRANSACTION_REJOUEE)

        # Un ecart est genere pour la transaction rejouee avec le statut REGULARISE
        ecart = EcartOM.objects.get(transid_om='REJOUEE', date_transaction=date_cible_2)
        self.assertEqual(ecart.type_ecart, EcartOM.TypeEcart.TRANSACTION_REJOUEE)
        self.assertEqual(ecart.statut, EcartOM.Statut.REGULARISE)


class NotificationNouveauxEcartsOMTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='op', email='op@example.com', password='x', is_email_verified=True,
        )
        self.date_cible = date(2026, 9, 7)
        self.patcher_derniere_activite = patch('transactions.services_rapprochement.fetch_derniere_activite')
        self.mock_derniere_activite = self.patcher_derniere_activite.start()
        self.mock_derniere_activite.return_value = journee_cbs_terminee(self.date_cible)
        self.addCleanup(self.patcher_derniere_activite.stop)

    @patch('transactions.services_pamf_om.fetch_transactions_pamf_om')
    def test_notifie_les_utilisateurs_verifies_si_nouveaux_ecarts(self, mock_fetch):
        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, '222')
        mock_fetch.return_value = []

        with self.captureOnCommitCallbacks(execute=True):
            lancer_rapprochement_om(self.date_cible, self.user)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)
        self.assertIn('222', mail.outbox[0].body)


class PrivilegeGatingOMViewTests(TestCase):
    """Le privilege importer_fichier_om est distinct de importer_csv_mvola (cf. CLAUDE.md,
    Decisions prises) : un utilisateur avec seulement l'un des deux n'a pas acces a l'autre."""

    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.client = Client()

    def test_import_om_refuse_sans_privilege(self):
        self.client.force_login(self.user)
        resp = self.client.get('/transactions/om/import/')
        self.assertEqual(resp.status_code, 403)

    def test_import_om_refuse_avec_seulement_importer_csv_mvola(self):
        grant_privilege(self.user, 'importer_csv_mvola')
        self.client.force_login(self.user)
        resp = self.client.get('/transactions/om/import/')
        self.assertEqual(resp.status_code, 403)

    def test_import_om_autorise_avec_le_bon_privilege(self):
        grant_privilege(self.user, 'importer_fichier_om')
        self.client.force_login(self.user)
        resp = self.client.get('/transactions/om/import/')
        self.assertEqual(resp.status_code, 200)

    def test_rapprochement_om_refuse_sans_privilege(self):
        self.client.force_login(self.user)
        resp = self.client.get('/transactions/om/rapprochement/')
        self.assertEqual(resp.status_code, 403)

    def test_rapprochement_om_autorise_avec_lancer_rapprochement(self):
        grant_privilege(self.user, 'lancer_rapprochement')
        self.client.force_login(self.user)
        resp = self.client.get('/transactions/om/rapprochement/')
        self.assertEqual(resp.status_code, 200)

    def test_liste_om_accessible_a_tout_utilisateur_connecte(self):
        self.client.force_login(self.user)
        resp = self.client.get('/transactions/om/transactions/')
        self.assertEqual(resp.status_code, 200)


class SmokeOMViewsTests(TestCase):
    """Verifie que les gabarits/URLs des ecrans OM restants (non couverts ailleurs) rendent sans
    erreur - filet de securite pour les erreurs de template/reverse non detectees par les tests
    plus cibles ci-dessus."""

    def setUp(self):
        self.user = User.objects.create_superuser(username='admin', email='admin@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.date_cible = date(2026, 9, 7)

        import_obj = make_import_om(self.user, date_fichier=self.date_cible)
        make_transaction_om(import_obj, '111')
        with patch('transactions.services_pamf_om.fetch_transactions_pamf_om') as mock_fetch, \
                patch('transactions.services_rapprochement.fetch_derniere_activite') as mock_derniere_activite:
            mock_fetch.return_value = []
            mock_derniere_activite.return_value = journee_cbs_terminee(self.date_cible)
            self.rapprochement = lancer_rapprochement_om(self.date_cible, self.user)

    def test_ecrans_om_rendent_sans_erreur(self):
        urls = [
            '/transactions/om/pamf/',
            f'/transactions/om/rapprochement/{self.rapprochement.pk}/detail/',
            f'/transactions/om/rapprochement/{self.rapprochement.pk}/lignes/om/',
            f'/transactions/om/rapprochement/{self.rapprochement.pk}/lignes/pamf/',
            f'/transactions/om/rapprochement/{self.rapprochement.pk}/lignes/orphelines/',
            '/transactions/om/transactions/export/excel/',
            '/transactions/om/transactions/export/pdf/',
            '/transactions/om/pamf/export/excel/',
            '/transactions/om/pamf/export/pdf/',
            f'/transactions/om/rapprochement/{self.rapprochement.pk}/lignes/orphelines/export/excel/',
            f'/transactions/om/rapprochement/{self.rapprochement.pk}/lignes/orphelines/export/pdf/',
            '/ecarts/om/ecarts/',
            '/ecarts/om/ecarts/export/excel/',
            '/ecarts/om/ecarts/export/pdf/',
        ]
        for url in urls:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200, f'{url} -> {resp.status_code}')

    def test_ecart_detail_om_rend_sans_erreur(self):
        from ecarts.models import EcartOM

        ecart = EcartOM.objects.get(transid_om='111')
        resp = self.client.get(f'/ecarts/om/ecarts/{ecart.pk}/')
        self.assertEqual(resp.status_code, 200)

    def test_sidebar_expose_le_lien_orange_money(self):
        resp = self.client.get('/')
        self.assertContains(resp, 'Orange Money')
        self.assertContains(resp, 'transactions/om/import/')
        # Airtel Money reste en placeholder desactive (cf. CLAUDE.md).
        self.assertContains(resp, 'Airtel Money')
        self.assertContains(resp, 'bientot')
