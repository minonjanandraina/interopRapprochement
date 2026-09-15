from django.db import migrations

from ..privileges import IMPORTER_FICHIER_OM, PRIVILEGE_CHOICES


def seed_importer_fichier_om(apps, schema_editor):
    Permission = apps.get_model('user', 'Permission')
    Role = apps.get_model('user', 'Role')

    label = dict(PRIVILEGE_CHOICES)[IMPORTER_FICHIER_OM]
    permission, _ = Permission.objects.get_or_create(code=IMPORTER_FICHIER_OM, defaults={'label': label})

    # Ajoute au role "Administrateur" existant (cf. 0003_seed_privileges) pour ne pas verrouiller
    # les superusers deja en place hors du nouvel ecran d'import Orange Money.
    admin_role = Role.objects.filter(name='Administrateur').first()
    if admin_role is not None:
        admin_role.permissions.add(permission)


def unseed_importer_fichier_om(apps, schema_editor):
    Permission = apps.get_model('user', 'Permission')
    Permission.objects.filter(code=IMPORTER_FICHIER_OM).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0004_seed_vue_only_privilege'),
    ]

    operations = [
        migrations.RunPython(seed_importer_fichier_om, unseed_importer_fichier_om),
    ]
