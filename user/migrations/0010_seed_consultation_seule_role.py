from django.db import migrations

from ..privileges import VUE_ONLY, CONSULTER_RAPPROCHEMENT


def seed_consultation_seule_role(apps, schema_editor):
    """Crée le rôle 'Consultation seule' avec les privilèges VUE_ONLY et CONSULTER_RAPPROCHEMENT."""
    Role = apps.get_model('user', 'Role')
    Permission = apps.get_model('user', 'Permission')

    try:
        vue_only_perm = Permission.objects.get(code=VUE_ONLY)
        consulter_perm = Permission.objects.get(code=CONSULTER_RAPPROCHEMENT)

        role, created = Role.objects.get_or_create(
            name='Consultation seule',
            defaults={'description': 'Accès en lecture seule aux données (consultation des rapprochements, listes, écarts).'},
        )

        if created or not role.permissions.filter(code=VUE_ONLY).exists():
            role.permissions.add(vue_only_perm)
        if not role.permissions.filter(code=CONSULTER_RAPPROCHEMENT).exists():
            role.permissions.add(consulter_perm)

        if created:
            print(f"Rôle 'Consultation seule' créé avec les privilèges: {VUE_ONLY}, {CONSULTER_RAPPROCHEMENT}")
    except Permission.DoesNotExist as e:
        print(f"Erreur: Privilège manquant - {e}")


def unseed_consultation_seule_role(apps, schema_editor):
    """Supprime le rôle 'Consultation seule'."""
    Role = apps.get_model('user', 'Role')
    Role.objects.filter(name='Consultation seule').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0009_alter_permission_code_choices'),
    ]

    operations = [
        migrations.RunPython(seed_consultation_seule_role, unseed_consultation_seule_role),
    ]
