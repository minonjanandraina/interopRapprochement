from django.db import migrations

from ..privileges import VUE_ONLY, CONSULTER_RAPPROCHEMENT


def add_consulter_rapprochement_to_vue_only_roles(apps, schema_editor):
    """Ajoute le privilege CONSULTER_RAPPROCHEMENT a tous les roles qui ont VUE_ONLY."""
    Role = apps.get_model('user', 'Role')
    Permission = apps.get_model('user', 'Permission')

    try:
        consulter_perm = Permission.objects.get(code=CONSULTER_RAPPROCHEMENT)
        vue_only_perm = Permission.objects.get(code=VUE_ONLY)

        # Trouve les roles qui ont VUE_ONLY et ajoute CONSULTER_RAPPROCHEMENT
        roles_with_vue_only = Role.objects.filter(permissions=vue_only_perm)
        for role in roles_with_vue_only:
            role.permissions.add(consulter_perm)
    except Permission.DoesNotExist:
        pass


def reverse_add_consulter_rapprochement_to_vue_only_roles(apps, schema_editor):
    """Supprime CONSULTER_RAPPROCHEMENT des roles qui l'ont."""
    Role = apps.get_model('user', 'Role')
    Permission = apps.get_model('user', 'Permission')

    try:
        consulter_perm = Permission.objects.get(code=CONSULTER_RAPPROCHEMENT)
        consulter_perm.role_set.clear()
    except Permission.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0007_seed_consulter_rapprochement'),
    ]

    operations = [
        migrations.RunPython(
            add_consulter_rapprochement_to_vue_only_roles,
            reverse_add_consulter_rapprochement_to_vue_only_roles
        ),
    ]
