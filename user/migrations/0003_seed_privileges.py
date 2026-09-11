from django.db import migrations

from ..privileges import PRIVILEGE_CHOICES


def seed_privileges(apps, schema_editor):
    Permission = apps.get_model('user', 'Permission')
    Role = apps.get_model('user', 'Role')
    User = apps.get_model('user', 'User')

    permissions = []
    for code, label in PRIVILEGE_CHOICES:
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'label': label})
        permissions.append(permission)

    # Role "Administrateur" avec tous les privileges, assigne aux superusers existants : evite
    # qu'un superuser se retrouve bloque par le nouveau systeme de privileges (cf. CLAUDE.md -
    # Sprint 6, durcissement securite ne doit pas se faire au prix d'un auto-verrouillage).
    admin_role, _ = Role.objects.get_or_create(
        name='Administrateur',
        defaults={'description': 'Tous les privileges (role cree automatiquement a l\'introduction des roles dynamiques).'},
    )
    admin_role.permissions.set(permissions)
    for user in User.objects.filter(is_superuser=True):
        user.roles.add(admin_role)


def unseed_privileges(apps, schema_editor):
    Role = apps.get_model('user', 'Role')
    Permission = apps.get_model('user', 'Permission')
    Role.objects.filter(name='Administrateur').delete()
    Permission.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0002_permission_role_user_roles'),
    ]

    operations = [
        migrations.RunPython(seed_privileges, unseed_privileges),
    ]
