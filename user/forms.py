from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm

from .models import Role, User


def _valider_email_unique(email):
    if User.objects.filter(email__iexact=email).exists():
        raise forms.ValidationError('Un compte existe deja avec cette adresse email.')
    return email


class RegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean_email(self):
        return _valider_email_unique(self.cleaned_data['email'])


class UtilisateurCreationForm(UserCreationForm):
    """Creation d'un utilisateur depuis l'ecran d'administration (pas le flux d'inscription
    publique) : l'admin definit directement le mot de passe, le compte est actif immediatement
    et l'email considere verifie (l'admin vouche pour la personne), cf. CLAUDE.md."""

    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all(), required=False, widget=forms.CheckboxSelectMultiple, label='Roles',
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != 'roles':
                field.widget.attrs.setdefault('class', 'form-control')

    def clean_email(self):
        return _valider_email_unique(self.cleaned_data['email'])


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ('name', 'description', 'permissions')
        widgets = {
            'permissions': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.setdefault('class', 'form-control')
        self.fields['description'].widget.attrs.setdefault('class', 'form-control')


class AssignerRolesForm(forms.Form):
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all(), required=False, widget=forms.CheckboxSelectMultiple,
    )


class DefinirMotDePasseForm(SetPasswordForm):
    """Reinitialisation du mot de passe d'un utilisateur par un administrateur (sans connaitre
    l'ancien mot de passe), cf. django.contrib.auth.forms.SetPasswordForm."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')
