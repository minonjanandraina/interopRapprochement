from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Permission, Role, User


@admin.register(User)
class InteropUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Verification email', {'fields': ('is_email_verified',)}),
        ('Roles dynamiques', {'fields': ('roles',)}),
    )
    filter_horizontal = UserAdmin.filter_horizontal + ('roles',)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_email_verified')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    filter_horizontal = ('permissions',)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('code', 'label')
