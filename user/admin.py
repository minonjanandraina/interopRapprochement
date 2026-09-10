from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class InteropUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Verification email', {'fields': ('is_email_verified',)}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_email_verified')
