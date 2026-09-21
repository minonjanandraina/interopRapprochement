from django.db import migrations

from ..privileges import CONSULTER_RAPPROCHEMENT, PRIVILEGE_CHOICES


def seed_consulter_rapprochement(apps, schema_editor):
    Permission = apps.get_model('user', 'Permission')
    Role = apps.get_model('user', 'Role')

    label = dict(PRIVILEGE_CHOICES)[CONSULTER_RAPPROCHEMENT]
    permission, _ = Permission.objects.get_or_create(code=CONSULTER_RAPPROCHEMENT, defaults={'label': label})

    # Ajoute au role "Administrateur" existant pour ne pas verrouiller les superusers en place.
    admin_role = Role.objects.filter(name='Administrateur').first()
    if admin_role is not None:
        admin_role.permissions.add(permission)


def unseed_consulter_rapprochement(apps, schema_editor):
    Permission = apps.get_model('user', 'Permission')
    Permission.objects.filter(code=CONSULTER_RAPPROCHEMENT).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0006_alter_permission_code'),
    ]

    operations = [
        migrations.RunPython(seed_consulter_rapprochement, unseed_consulter_rapprochement),
    ]
