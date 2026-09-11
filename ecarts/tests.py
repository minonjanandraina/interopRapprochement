from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from transactions.csv_mvola import importer_fichier_mvola
from transactions.services_rapprochement import lancer_rapprochement
from transactions.tests import make_csv, make_row
from user import privileges
from user.models import Permission, Role

from .models import Ecart, EcartHistorique

User = get_user_model()


def grant_privilege(user, code):
    permission = Permission.objects.get(code=code)
    role = Role.objects.create(name=f'role-{code}-{user.pk}')
    role.permissions.add(permission)
    user.roles.add(role)


class ListeEcartViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)

        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111'), make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        with patch('transactions.services_pamf.fetch_transactions_pamf') as mock_fetch:
            mock_fetch.return_value = [
                {'rAutotransactionID': 1, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': '', 'TRANSID_MVOLA': '111', 'responseBody': ''},
            ]
            lancer_rapprochement(date(2026, 9, 7), self.user)
        # '111' est rapprochee (SUCCESS), '222' est orpheline MVOLA -> un seul Ecart attendu.

    def test_affiche_les_ecarts_orphelins_seulement(self):
        resp = self.client.get('/ecarts/mvola/ecarts/')
        self.assertContains(resp, '222')
        self.assertNotContains(resp, '111')

    def test_filtre_par_statut(self):
        ecart = Ecart.objects.get(transid_mvola='222')
        ecart.statut = Ecart.Statut.REGULARISE
        ecart.save()

        resp = self.client.get('/ecarts/mvola/ecarts/', {'statut': 'REGULARISE'})
        self.assertContains(resp, '222')

        resp2 = self.client.get('/ecarts/mvola/ecarts/', {'statut': 'DETECTE'})
        self.assertNotContains(resp2, '222')

    def test_filtre_par_type_ecart(self):
        resp = self.client.get('/ecarts/mvola/ecarts/', {'type_ecart': 'ORPHELINE_MVOLA'})
        self.assertContains(resp, '222')

        resp2 = self.client.get('/ecarts/mvola/ecarts/', {'type_ecart': 'ORPHELINE_PAMF'})
        self.assertNotContains(resp2, '222')

    def test_affiche_le_montant_de_la_transaction_mvola(self):
        ecart = Ecart.objects.get(transid_mvola='222')
        self.assertEqual(ecart.montant, Decimal('299600.00'))

        resp = self.client.get('/ecarts/mvola/ecarts/')
        self.assertContains(resp, '299600')

    def test_orpheline_pamf_na_pas_de_montant(self):
        """La requete CBS ne remonte pas de montant : rien a afficher pour une ORPHELINE_PAMF."""
        with patch('transactions.services_pamf.fetch_transactions_pamf') as mock_fetch:
            mock_fetch.return_value = [
                {'rAutotransactionID': 1, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': '', 'TRANSID_MVOLA': '111', 'responseBody': ''},
                {'rAutotransactionID': 2, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': '', 'TRANSID_MVOLA': '999', 'responseBody': ''},
            ]
            lancer_rapprochement(date(2026, 9, 7), self.user)

        ecart_pamf = Ecart.objects.get(transid_mvola='999')
        self.assertEqual(ecart_pamf.type_ecart, Ecart.TypeEcart.ORPHELINE_PAMF)
        self.assertIsNone(ecart_pamf.montant)

    def test_export_excel_respecte_le_filtre_de_statut(self):
        resp = self.client.get('/ecarts/mvola/ecarts/export/excel/', {'statut': 'DETECTE'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('ecarts_mvola.xlsx', resp['Content-Disposition'])

    def test_export_pdf(self):
        resp = self.client.get('/ecarts/mvola/ecarts/export/pdf/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('ecarts_mvola.pdf', resp['Content-Disposition'])

    def test_entete_de_rapport_affiche_les_filtres_et_le_total(self):
        resp = self.client.get('/ecarts/mvola/ecarts/', {'type_ecart': 'ORPHELINE_MVOLA'})
        self.assertContains(resp, 'Type = Orpheline MVOLA')
        self.assertContains(resp, '1 ligne')


class DetailEcartViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        grant_privilege(self.user, privileges.TRAITER_ECARTS)
        self.client = Client()
        self.client.force_login(self.user)

        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='111'), make_row(transid='222')])
        importer_fichier_mvola(fichier, self.user)
        with patch('transactions.services_pamf.fetch_transactions_pamf') as mock_fetch:
            mock_fetch.return_value = [
                {'rAutotransactionID': 1, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': 'note pamf', 'TRANSID_MVOLA': '111', 'responseBody': '{"ok": true}'},
            ]
            lancer_rapprochement(date(2026, 9, 7), self.user)
        self.ecart_orpheline_mvola = Ecart.objects.get(transid_mvola='222')

    def test_detail_orpheline_mvola_affiche_mvola_et_absence_pamf(self):
        resp = self.client.get(f'/ecarts/mvola/ecarts/{self.ecart_orpheline_mvola.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '222')
        self.assertContains(resp, 'Aucune transaction PAMF')

    def test_ajouter_commentaire_cree_une_entree_historique(self):
        resp = self.client.post(
            f'/ecarts/mvola/ecarts/{self.ecart_orpheline_mvola.pk}/commentaire/',
            {'texte': 'en cours de verification aupres de la banque'}, follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        entree = EcartHistorique.objects.get(ecart=self.ecart_orpheline_mvola)
        self.assertEqual(entree.action, EcartHistorique.Action.COMMENTAIRE)
        self.assertEqual(entree.auteur, self.user)
        self.assertEqual(entree.commentaire, 'en cours de verification aupres de la banque')

    def test_changer_statut_met_a_jour_ecart_et_cree_lhistorique(self):
        self.client.post(
            f'/ecarts/mvola/ecarts/{self.ecart_orpheline_mvola.pk}/statut/',
            {'nouveau_statut': Ecart.Statut.REGULARISE}, follow=True,
        )
        self.ecart_orpheline_mvola.refresh_from_db()
        self.assertEqual(self.ecart_orpheline_mvola.statut, Ecart.Statut.REGULARISE)

        entree = EcartHistorique.objects.get(ecart=self.ecart_orpheline_mvola)
        self.assertEqual(entree.action, EcartHistorique.Action.CHANGEMENT_STATUT)
        self.assertEqual(entree.ancien_statut, Ecart.Statut.DETECTE)
        self.assertEqual(entree.nouveau_statut, Ecart.Statut.REGULARISE)

    def test_changer_statut_identique_ne_cree_pas_dentree(self):
        self.client.post(
            f'/ecarts/mvola/ecarts/{self.ecart_orpheline_mvola.pk}/statut/',
            {'nouveau_statut': Ecart.Statut.DETECTE}, follow=True,
        )
        self.assertEqual(EcartHistorique.objects.filter(ecart=self.ecart_orpheline_mvola).count(), 0)

    def test_ajouter_piece_jointe_cree_une_entree_historique_avec_fichier(self):
        fichier = SimpleUploadedFile('preuve.txt', b'contenu de la preuve', content_type='text/plain')
        resp = self.client.post(
            f'/ecarts/mvola/ecarts/{self.ecart_orpheline_mvola.pk}/piece-jointe/',
            {'fichier': fichier, 'commentaire': 'preuve du virement'}, follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        entree = EcartHistorique.objects.get(ecart=self.ecart_orpheline_mvola)
        self.assertEqual(entree.action, EcartHistorique.Action.PIECE_JOINTE)
        self.assertTrue(entree.fichier.name.endswith('preuve.txt'))
        entree.fichier.delete(save=False)

    def test_ecart_sans_ligne_pamf_recommande_un_rollback(self):
        """Aucune ligne PAMF -> la requete n'a pas atteint Aspekt -> rollback MVOLA recommande."""
        self.assertEqual(self.ecart_orpheline_mvola.action_recommandee, 'ROLLBACK_MVOLA')

    def test_confirmer_rollback_cree_une_entree_historique(self):
        resp = self.client.post(
            f'/ecarts/mvola/ecarts/{self.ecart_orpheline_mvola.pk}/rollback-confirme/',
            {'reference': 'rembourse le 10/09'}, follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        entree = EcartHistorique.objects.get(ecart=self.ecart_orpheline_mvola)
        self.assertEqual(entree.action, EcartHistorique.Action.ROLLBACK_CONFIRME)
        self.assertEqual(entree.reference_externe, 'rembourse le 10/09')
        self.assertEqual(entree.auteur, self.user)


class TicketAspektViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')
        grant_privilege(self.user, privileges.TRAITER_ECARTS)
        self.client = Client()
        self.client.force_login(self.user)

        fichier = make_csv('2026-09-07_reporting_PAMF.csv', [make_row(transid='555')])
        importer_fichier_mvola(fichier, self.user)
        with patch('transactions.services_pamf.fetch_transactions_pamf') as mock_fetch:
            mock_fetch.return_value = [
                {'rAutotransactionID': 9, 'postingDate': date(2026, 9, 7), 'Time': '00:00:00',
                 'Note': '', 'TRANSID_MVOLA': '555', 'responseBody': '', 'is_sucess': 0},
            ]
            lancer_rapprochement(date(2026, 9, 7), self.user)
        self.ecart = Ecart.objects.get(transid_mvola='555')

    def test_ecart_avec_pamf_en_echec_recommande_un_ticket_aspekt(self):
        """Une ligne PAMF existe (en echec) -> la requete a atteint Aspekt -> ticket recommande."""
        self.assertEqual(self.ecart.action_recommandee, 'TICKET_ASPEKT')

    def test_enregistrer_ticket_aspekt_cree_une_entree_historique(self):
        resp = self.client.post(
            f'/ecarts/mvola/ecarts/{self.ecart.pk}/ticket-aspekt/',
            {'reference': 'ASP-2026-00042'}, follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        entree = EcartHistorique.objects.get(ecart=self.ecart)
        self.assertEqual(entree.action, EcartHistorique.Action.TICKET_ASPEKT)
        self.assertEqual(entree.reference_externe, 'ASP-2026-00042')
        self.assertEqual(entree.auteur, self.user)
