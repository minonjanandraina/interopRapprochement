"""Tests Orange Money (OM) - miroir cible des points a risque de tests.py (MVOLA), pas une copie
ligne a ligne : cf. CLAUDE.md, Decisions prises (duplication OM)."""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from transactions.models import TransactionPamfOM
from transactions.services_rapprochement_om import lancer_rapprochement_om
from transactions.tests_om import journee_cbs_terminee, make_import_om, make_transaction_om
from user import privileges
from user.models import Permission, Role

from .models import EcartHistoriqueOM, EcartOM

User = get_user_model()


def grant_privilege(user, code):
    permission = Permission.objects.get(code=code)
    role = Role.objects.create(name=f'role-{code}-{user.pk}')
    role.permissions.add(permission)
    user.roles.add(role)


class ListeEcartOMViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)

        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, '111')
        make_transaction_om(import_obj, '222')
        with patch('transactions.services_pamf_om.fetch_transactions_pamf_om') as mock_fetch, \
                patch('transactions.services_rapprochement.fetch_derniere_activite') as mock_derniere_activite:
            mock_fetch.return_value = [
                {'rAutotransactionID': 1, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': '', 'TRANSID_ORANGE_MONEY': '111', 'responseBody': ''},
            ]
            mock_derniere_activite.return_value = journee_cbs_terminee(date(2026, 9, 7))
            lancer_rapprochement_om(date(2026, 9, 7), self.user)
        # '111' est rapprochee (SUCCESS), '222' est orpheline OM -> un seul EcartOM attendu.

    def test_affiche_les_ecarts_orphelins_seulement(self):
        resp = self.client.get('/ecarts/om/ecarts/')
        self.assertContains(resp, '222')
        self.assertNotContains(resp, '111')

    def test_filtre_par_statut(self):
        ecart = EcartOM.objects.get(transid_om='222')
        ecart.statut = EcartOM.Statut.REGULARISE
        ecart.save()

        resp = self.client.get('/ecarts/om/ecarts/', {'statut': 'REGULARISE'})
        self.assertContains(resp, '222')

        resp2 = self.client.get('/ecarts/om/ecarts/', {'statut': 'DETECTE'})
        self.assertNotContains(resp2, '222')

    def test_affiche_le_montant_de_la_transaction_om(self):
        ecart = EcartOM.objects.get(transid_om='222')
        self.assertEqual(ecart.montant, 10000)


class RollbackOMViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        grant_privilege(self.user, privileges.TRAITER_ECARTS)
        self.client = Client()
        self.client.force_login(self.user)

        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, '333')
        with patch('transactions.services_pamf_om.fetch_transactions_pamf_om') as mock_fetch, \
                patch('transactions.services_rapprochement.fetch_derniere_activite') as mock_derniere_activite:
            mock_fetch.return_value = []
            mock_derniere_activite.return_value = journee_cbs_terminee(date(2026, 9, 7))
            lancer_rapprochement_om(date(2026, 9, 7), self.user)
        self.ecart = EcartOM.objects.get(transid_om='333')

    def test_ecart_sans_ligne_pamf_recommande_un_rollback(self):
        self.assertEqual(self.ecart.action_recommandee, 'ROLLBACK_OM')

    def test_confirmer_rollback_cree_une_entree_historique(self):
        resp = self.client.post(
            f'/ecarts/om/ecarts/{self.ecart.pk}/rollback-confirme/',
            {'reference': 'rembourse le 10/09'}, follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        entree = EcartHistoriqueOM.objects.get(ecart=self.ecart)
        self.assertEqual(entree.action, EcartHistoriqueOM.Action.ROLLBACK_CONFIRME)
        self.assertEqual(entree.reference_externe, 'rembourse le 10/09')
        self.assertEqual(entree.auteur, self.user)

    def test_ajouter_commentaire_cree_une_entree_historique(self):
        resp = self.client.post(
            f'/ecarts/om/ecarts/{self.ecart.pk}/commentaire/', {'texte': 'en cours'}, follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        entree = EcartHistoriqueOM.objects.get(ecart=self.ecart)
        self.assertEqual(entree.action, EcartHistoriqueOM.Action.COMMENTAIRE)

    def test_ajouter_piece_jointe_cree_une_entree_historique_avec_fichier(self):
        fichier = SimpleUploadedFile('preuve.txt', b'contenu de la preuve', content_type='text/plain')
        resp = self.client.post(
            f'/ecarts/om/ecarts/{self.ecart.pk}/piece-jointe/',
            {'fichier': fichier, 'commentaire': 'preuve du virement'}, follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        entree = EcartHistoriqueOM.objects.get(ecart=self.ecart)
        self.assertEqual(entree.action, EcartHistoriqueOM.Action.PIECE_JOINTE)
        self.assertTrue(entree.fichier.name.endswith('preuve.txt'))
        entree.fichier.delete(save=False)

    def test_sans_privilege_refuse(self):
        autre_user = User.objects.create_user(username='sans-droit', email='sd@example.com', password='x')
        self.client.force_login(autre_user)
        resp = self.client.post(
            f'/ecarts/om/ecarts/{self.ecart.pk}/rollback-confirme/', {'reference': 'x'},
        )
        self.assertEqual(resp.status_code, 403)


class TicketAspektOMViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        grant_privilege(self.user, privileges.TRAITER_ECARTS)
        self.client = Client()
        self.client.force_login(self.user)

        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, '555')
        with patch('transactions.services_pamf_om.fetch_transactions_pamf_om') as mock_fetch, \
                patch('transactions.services_rapprochement.fetch_derniere_activite') as mock_derniere_activite:
            mock_fetch.return_value = [
                {'rAutotransactionID': 9, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': '', 'TRANSID_ORANGE_MONEY': '555', 'responseBody': '', 'is_sucess': 0},
            ]
            mock_derniere_activite.return_value = journee_cbs_terminee(date(2026, 9, 7))
            lancer_rapprochement_om(date(2026, 9, 7), self.user)
        self.ecart = EcartOM.objects.get(transid_om='555')

    def test_ecart_avec_pamf_en_echec_recommande_un_ticket_aspekt(self):
        self.assertEqual(self.ecart.action_recommandee, 'TICKET_ASPEKT')

    def test_enregistrer_ticket_aspekt_cree_une_entree_historique(self):
        resp = self.client.post(
            f'/ecarts/om/ecarts/{self.ecart.pk}/ticket-aspekt/',
            {'reference': 'ASP-2026-00042'}, follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        entree = EcartHistoriqueOM.objects.get(ecart=self.ecart)
        self.assertEqual(entree.action, EcartHistoriqueOM.Action.TICKET_ASPEKT)
        self.assertEqual(entree.reference_externe, 'ASP-2026-00042')
        self.assertEqual(entree.auteur, self.user)


class DoublonPamfOMViewTests(TestCase):
    """cf. CLAUDE.md - decision du 2026-09-15 : un transid_om avec plusieurs postings PAMF n'est
    plus resolu automatiquement, l'agent choisit le posting de reference."""

    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        grant_privilege(self.user, privileges.TRAITER_ECARTS)
        self.client = Client()
        self.client.force_login(self.user)

        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, 'SPLIT')
        with patch('transactions.services_pamf_om.fetch_transactions_pamf_om') as mock_fetch, \
                patch('transactions.services_rapprochement.fetch_derniere_activite') as mock_derniere_activite:
            mock_fetch.return_value = [
                {'rAutotransactionID': 111, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': 'pret 1', 'TRANSID_ORANGE_MONEY': 'SPLIT', 'responseBody': '', 'is_sucess': 1},
                {'rAutotransactionID': 222, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': 'pret 2', 'TRANSID_ORANGE_MONEY': 'SPLIT', 'responseBody': '', 'is_sucess': 0},
            ]
            mock_derniere_activite.return_value = journee_cbs_terminee(date(2026, 9, 7))
            lancer_rapprochement_om(date(2026, 9, 7), self.user)
        self.ecart = EcartOM.objects.get(transid_om='SPLIT')

    def test_ecart_avec_plusieurs_postings_recommande_de_choisir_le_posting(self):
        self.assertEqual(self.ecart.action_recommandee, 'CHOISIR_POSTING')

    def test_choisir_un_posting_cree_une_entree_historique_et_leve_laction_recommandee(self):
        candidat = TransactionPamfOM.objects.get(transid_om='SPLIT', r_autotransaction_id='222')
        resp = self.client.post(
            f'/ecarts/om/ecarts/{self.ecart.pk}/resoudre-doublon/',
            {'transaction_pamf_id': candidat.pk}, follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        entree = EcartHistoriqueOM.objects.get(ecart=self.ecart)
        self.assertEqual(entree.action, EcartHistoriqueOM.Action.RESOLUTION_DOUBLON)
        self.assertEqual(entree.reference_externe, '222')

        self.ecart.refresh_from_db()
        self.assertIsNone(self.ecart.action_recommandee)

    def test_sans_privilege_refuse(self):
        autre_user = User.objects.create_user(username='sans-droit', email='sd@example.com', password='x')
        self.client.force_login(autre_user)
        candidat = TransactionPamfOM.objects.get(transid_om='SPLIT', r_autotransaction_id='111')
        resp = self.client.post(
            f'/ecarts/om/ecarts/{self.ecart.pk}/resoudre-doublon/',
            {'transaction_pamf_id': candidat.pk},
        )
        self.assertEqual(resp.status_code, 403)


class BulkActionOMViewTests(TestCase):
    """Cf. ecarts.tests.BulkActionViewTests (MVOLA) - meme mecanisme pour Orange Money."""

    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        grant_privilege(self.user, privileges.TRAITER_ECARTS)
        self.client = Client()
        self.client.force_login(self.user)

        import_obj = make_import_om(self.user)
        make_transaction_om(import_obj, '111')
        make_transaction_om(import_obj, '222')
        make_transaction_om(import_obj, '333')
        with patch('transactions.services_pamf_om.fetch_transactions_pamf_om') as mock_fetch, \
                patch('transactions.services_rapprochement.fetch_derniere_activite') as mock_derniere_activite:
            mock_fetch.return_value = []
            mock_derniere_activite.return_value = journee_cbs_terminee(date(2026, 9, 7))
            lancer_rapprochement_om(date(2026, 9, 7), self.user)
        # '111'/'222'/'333' sont toutes orphelines OM (aucune ligne PAMF).
        self.ecart1 = EcartOM.objects.get(transid_om='111')
        self.ecart2 = EcartOM.objects.get(transid_om='222')
        self.ecart3 = EcartOM.objects.get(transid_om='333')

    def test_changer_statut_en_masse_met_a_jour_les_ecarts_coches_seulement(self):
        resp = self.client.post(
            '/ecarts/om/ecarts/action-masse/',
            {'action': 'statut', 'nouveau_statut': EcartOM.Statut.EN_COURS,
             'ecart_ids': [self.ecart1.pk, self.ecart2.pk]},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.ecart1.refresh_from_db()
        self.ecart2.refresh_from_db()
        self.ecart3.refresh_from_db()
        self.assertEqual(self.ecart1.statut, EcartOM.Statut.EN_COURS)
        self.assertEqual(self.ecart2.statut, EcartOM.Statut.EN_COURS)
        self.assertEqual(self.ecart3.statut, EcartOM.Statut.DETECTE)
        self.assertEqual(
            EcartHistoriqueOM.objects.filter(action=EcartHistoriqueOM.Action.CHANGEMENT_STATUT).count(), 2,
        )

    def test_ajouter_commentaire_en_masse_cree_une_entree_par_ecart_coche(self):
        self.client.post(
            '/ecarts/om/ecarts/action-masse/',
            {'action': 'commentaire', 'texte': 'relance groupee', 'ecart_ids': [self.ecart1.pk, self.ecart3.pk]},
            follow=True,
        )
        self.assertEqual(
            EcartHistoriqueOM.objects.filter(action=EcartHistoriqueOM.Action.COMMENTAIRE, commentaire='relance groupee').count(), 2,
        )
        self.assertFalse(EcartHistoriqueOM.objects.filter(ecart=self.ecart2).exists())

    def test_enregistrer_ticket_aspekt_en_masse(self):
        self.client.post(
            '/ecarts/om/ecarts/action-masse/',
            {'action': 'ticket_aspekt', 'reference': 'ASP-1000', 'ecart_ids': [self.ecart1.pk]},
            follow=True,
        )
        entree = EcartHistoriqueOM.objects.get(ecart=self.ecart1)
        self.assertEqual(entree.action, EcartHistoriqueOM.Action.TICKET_ASPEKT)
        self.assertEqual(entree.reference_externe, 'ASP-1000')

    def test_sans_selection_ne_modifie_rien(self):
        resp = self.client.post(
            '/ecarts/om/ecarts/action-masse/',
            {'action': 'statut', 'nouveau_statut': EcartOM.Statut.EN_COURS}, follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.ecart1.refresh_from_db()
        self.assertEqual(self.ecart1.statut, EcartOM.Statut.DETECTE)

    def test_sans_privilege_refuse(self):
        autre_user = User.objects.create_user(username='sans-droit', email='sd@example.com', password='x')
        self.client.force_login(autre_user)
        resp = self.client.post(
            '/ecarts/om/ecarts/action-masse/',
            {'action': 'statut', 'nouveau_statut': EcartOM.Statut.EN_COURS, 'ecart_ids': [self.ecart1.pk]},
        )
        self.assertEqual(resp.status_code, 403)
