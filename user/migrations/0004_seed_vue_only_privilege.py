from django.db import migrations

from ..privileges import VUE_ONLY, PRIVILEGE_CHOICES


def seed_vue_only(apps, schema_editor):
    Permission = apps.get_model('user', 'Permission')
    label = dict(PRIVILEGE_CHOICES)[VUE_ONLY]
    Permission.objects.get_or_create(code=VUE_ONLY, defaults={'label': label})


def unseed_vue_only(apps, schema_editor):
    Permission = apps.get_model('user', 'Permission')
    Permission.objects.filter(code=VUE_ONLY).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0003_seed_privileges'),
    ]

    operations = [
        migrations.RunPython(seed_vue_only, unseed_vue_only),
    ]
