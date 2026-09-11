from django.test import TestCase

from . import privileges
from .models import Permission, Role, User


class HasPrivilegeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='op', email='op@example.com', password='x')

    def test_utilisateur_sans_role_na_aucun_privilege(self):
        self.assertFalse(self.user.has_privilege(privileges.GERER_ROLES))

    def test_privilege_accorde_via_un_role_assigne(self):
        role = Role.objects.create(name='Agent')
        role.permissions.add(Permission.objects.get(code=privileges.TRAITER_ECARTS))
        self.user.roles.add(role)
        self.assertTrue(self.user.has_privilege(privileges.TRAITER_ECARTS))
        self.assertFalse(self.user.has_privilege(privileges.GERER_ROLES))

    def test_superuser_a_tous_les_privileges_sans_role(self):
        admin = User.objects.create_superuser(username='admin', email='admin@example.com', password='x')
        self.assertTrue(admin.has_privilege(privileges.GERER_ROLES))
        self.assertTrue(admin.has_privilege(privileges.TRAITER_ECARTS))

    def test_migration_seed_cree_le_role_administrateur_pour_les_superusers_existants(self):
        """Cf. migration user.0003_seed_privileges : ne pas verrouiller les superusers existants."""
        role = Role.objects.get(name='Administrateur')
        self.assertEqual(role.permissions.count(), len(privileges.PRIVILEGE_CHOICES))


class RoleViewsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', email='admin@example.com', password='x')
        role_gerer_roles = Role.objects.create(name='Gestionnaire de roles')
        role_gerer_roles.permissions.add(Permission.objects.get(code=privileges.GERER_ROLES))
        self.admin.roles.add(role_gerer_roles)
        self.client.force_login(self.admin)

    def test_utilisateur_sans_privilege_recoit_un_403(self):
        autre = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.client.force_login(autre)
        resp = self.client.get('/compte/roles/')
        self.assertEqual(resp.status_code, 403)

    def test_creer_un_role(self):
        resp = self.client.post('/compte/roles/nouveau/', {
            'name': 'Agent regularisation',
            'description': 'Traite les ecarts au quotidien',
            'permissions': [Permission.objects.get(code=privileges.TRAITER_ECARTS).pk],
        })
        self.assertRedirects(resp, '/compte/roles/')
        role = Role.objects.get(name='Agent regularisation')
        self.assertTrue(role.permissions.filter(code=privileges.TRAITER_ECARTS).exists())

    def test_modifier_les_privileges_dun_role(self):
        role = Role.objects.create(name='Agent')
        resp = self.client.post(f'/compte/roles/{role.pk}/modifier/', {
            'name': 'Agent',
            'description': '',
            'permissions': [Permission.objects.get(code=privileges.LANCER_RAPPROCHEMENT).pk],
        })
        self.assertRedirects(resp, '/compte/roles/')
        role.refresh_from_db()
        self.assertTrue(role.permissions.filter(code=privileges.LANCER_RAPPROCHEMENT).exists())

    def test_suppression_bloquee_si_role_assigne_a_un_utilisateur(self):
        role = Role.objects.create(name='Agent')
        autre = User.objects.create_user(username='op', email='op@example.com', password='x')
        autre.roles.add(role)

        resp = self.client.post(f'/compte/roles/{role.pk}/supprimer/', follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Role.objects.filter(pk=role.pk).exists())

    def test_suppression_autorisee_si_role_non_assigne(self):
        role = Role.objects.create(name='Agent')
        resp = self.client.post(f'/compte/roles/{role.pk}/supprimer/')
        self.assertRedirects(resp, '/compte/roles/')
        self.assertFalse(Role.objects.filter(pk=role.pk).exists())


class UtilisateurRolesViewsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', email='admin@example.com', password='x')
        role_gerer_utilisateurs = Role.objects.create(name='Gestionnaire utilisateurs')
        role_gerer_utilisateurs.permissions.add(Permission.objects.get(code=privileges.GERER_UTILISATEURS))
        self.admin.roles.add(role_gerer_utilisateurs)
        self.client.force_login(self.admin)

    def test_assigner_un_role_a_un_utilisateur(self):
        agent_role = Role.objects.create(name='Agent')
        cible = User.objects.create_user(username='op', email='op@example.com', password='x')

        resp = self.client.post(f'/compte/utilisateurs/{cible.pk}/roles/', {'roles': [agent_role.pk]})
        self.assertRedirects(resp, '/compte/utilisateurs/')
        self.assertIn(agent_role, cible.roles.all())

    def test_retirer_tous_les_roles_dun_utilisateur(self):
        agent_role = Role.objects.create(name='Agent')
        cible = User.objects.create_user(username='op', email='op@example.com', password='x')
        cible.roles.add(agent_role)

        self.client.post(f'/compte/utilisateurs/{cible.pk}/roles/', {'roles': []})
        self.assertEqual(cible.roles.count(), 0)

    def test_creer_un_utilisateur_actif_et_verifie_avec_roles(self):
        agent_role = Role.objects.create(name='Agent')

        resp = self.client.post('/compte/utilisateurs/nouveau/', {
            'username': 'nouvel_agent',
            'email': 'nouvel_agent@example.com',
            'first_name': 'Nouvel',
            'last_name': 'Agent',
            'password1': 'un-mot-de-passe-solide-42',
            'password2': 'un-mot-de-passe-solide-42',
            'roles': [agent_role.pk],
        })
        self.assertRedirects(resp, '/compte/utilisateurs/')

        cree = User.objects.get(username='nouvel_agent')
        self.assertTrue(cree.is_active)
        self.assertTrue(cree.is_email_verified)
        self.assertTrue(cree.check_password('un-mot-de-passe-solide-42'))
        self.assertIn(agent_role, cree.roles.all())

    def test_creation_refuse_un_email_deja_utilise(self):
        User.objects.create_user(username='existant', email='dup@example.com', password='x')

        resp = self.client.post('/compte/utilisateurs/nouveau/', {
            'username': 'autre',
            'email': 'dup@example.com',
            'password1': 'un-mot-de-passe-solide-42',
            'password2': 'un-mot-de-passe-solide-42',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username='autre').exists())

    def test_desactiver_puis_reactiver_un_utilisateur(self):
        cible = User.objects.create_user(username='op', email='op@example.com', password='x')
        self.assertTrue(cible.is_active)

        self.client.post(f'/compte/utilisateurs/{cible.pk}/activer-desactiver/')
        cible.refresh_from_db()
        self.assertFalse(cible.is_active)

        self.client.post(f'/compte/utilisateurs/{cible.pk}/activer-desactiver/')
        cible.refresh_from_db()
        self.assertTrue(cible.is_active)

    def test_un_administrateur_ne_peut_pas_se_desactiver_lui_meme(self):
        self.client.post(f'/compte/utilisateurs/{self.admin.pk}/activer-desactiver/')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_utilisateur_desactive_ne_peut_plus_se_connecter(self):
        cible = User.objects.create_user(username='op', email='op@example.com', password='motdepasse123')
        self.client.post(f'/compte/utilisateurs/{cible.pk}/activer-desactiver/')

        connecte = self.client.login(username='op', password='motdepasse123')
        self.assertFalse(connecte)

    def test_reinitialiser_le_mot_de_passe_dun_utilisateur(self):
        cible = User.objects.create_user(username='op', email='op@example.com', password='ancien-mdp')

        resp = self.client.post(f'/compte/utilisateurs/{cible.pk}/mot-de-passe/', {
            'new_password1': 'nouveau-mdp-solide-99',
            'new_password2': 'nouveau-mdp-solide-99',
        })
        self.assertRedirects(resp, '/compte/utilisateurs/')

        cible.refresh_from_db()
        self.assertTrue(cible.check_password('nouveau-mdp-solide-99'))
        self.assertFalse(cible.check_password('ancien-mdp'))
