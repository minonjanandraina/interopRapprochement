from django.contrib.auth.models import AbstractUser
from django.db import models

from .privileges import GERER_ROLES as PRIVILEGE_GERER_ROLES
from .privileges import GERER_UTILISATEURS as PRIVILEGE_GERER_UTILISATEURS
from .privileges import IMPORTER_CSV_MVOLA as PRIVILEGE_IMPORTER_CSV_MVOLA
from .privileges import IMPORTER_FICHIER_OM as PRIVILEGE_IMPORTER_FICHIER_OM
from .privileges import LANCER_RAPPROCHEMENT as PRIVILEGE_LANCER_RAPPROCHEMENT
from .privileges import PRIVILEGE_CHOICES


class Permission(models.Model):
    """Un privilege du catalogue fixe (cf. user.privileges), assignable a des roles."""

    code = models.CharField(max_length=50, unique=True, choices=PRIVILEGE_CHOICES)
    label = models.CharField(max_length=255)

    class Meta:
        ordering = ['label']

    def __str__(self):
        return self.label


class Role(models.Model):
    """Role dynamique : cree/modifie/supprime depuis l'interface (cf. CLAUDE.md - Sprint 6)."""

    name = models.CharField('nom', max_length=100, unique=True)
    description = models.TextField('description', blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name='roles', verbose_name='privileges')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class User(AbstractUser):
    email = models.EmailField('adresse email', unique=True)
    is_email_verified = models.BooleanField('email verifie', default=False)
    roles = models.ManyToManyField(Role, blank=True, related_name='users', verbose_name='roles')

    def __str__(self):
        return self.get_username()

    def has_privilege(self, code):
        if self.is_superuser:
            return True
        return self.roles.filter(permissions__code=code).exists()

    @property
    def roles_display(self):
        return ', '.join(role.name for role in self.roles.all()) or '-'

    @property
    def peut_importer_csv_mvola(self):
        return self.has_privilege(PRIVILEGE_IMPORTER_CSV_MVOLA)

    @property
    def peut_importer_fichier_om(self):
        return self.has_privilege(PRIVILEGE_IMPORTER_FICHIER_OM)

    @property
    def peut_lancer_rapprochement(self):
        return self.has_privilege(PRIVILEGE_LANCER_RAPPROCHEMENT)

    @property
    def peut_gerer_roles(self):
        return self.has_privilege(PRIVILEGE_GERER_ROLES)

    @property
    def peut_gerer_utilisateurs(self):
        return self.has_privilege(PRIVILEGE_GERER_UTILISATEURS)
