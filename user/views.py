from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.generic import FormView

from . import privileges
from .decorators import privilege_required
from .forms import AssignerRolesForm, DefinirMotDePasseForm, RegistrationForm, RoleForm, UtilisateurCreationForm
from .models import Role, User
from .tokens import account_activation_token


def _send_activation_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = account_activation_token.make_token(user)
    activation_path = reverse('user:activate', kwargs={'uidb64': uid, 'token': token})
    activation_url = f'{settings.SITE_BASE_URL}{activation_path}'
    message = render_to_string('user/emails/activation_email.txt', {
        'user': user,
        'activation_url': activation_url,
    })
    send_mail(
        subject="Activation de votre compte - interopRapprochement",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


class RegisterView(FormView):
    template_name = 'user/register.html'
    form_class = RegistrationForm

    def form_valid(self, form):
        user = form.save(commit=False)
        user.is_active = False
        user.save()
        _send_activation_email(self.request, user)
        return render(self.request, 'user/activation_sent.html', {'email': user.email})


def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.is_email_verified = True
        user.save(update_fields=['is_active', 'is_email_verified'])
        messages.success(request, "Votre adresse email a ete verifiee, vous pouvez maintenant vous connecter.")
        return redirect('user:login')

    return render(request, 'user/activation_invalid.html')


class InteropLoginView(LoginView):
    template_name = 'user/login.html'


class InteropLogoutView(LogoutView):
    pass


@privilege_required(privileges.GERER_ROLES)
def roles_liste(request):
    roles = Role.objects.prefetch_related('permissions', 'users')
    return render(request, 'user/roles_liste.html', {'roles': roles, 'active_admin_tab': 'roles'})


@privilege_required(privileges.GERER_ROLES)
def role_creer(request):
    if request.method == 'POST':
        form = RoleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Role \"{form.cleaned_data['name']}\" cree.")
            return redirect('user:roles_liste')
    else:
        form = RoleForm()
    return render(request, 'user/role_form.html', {
        'form': form, 'titre': 'Nouveau role', 'active_admin_tab': 'roles',
    })


@privilege_required(privileges.GERER_ROLES)
def role_modifier(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if request.method == 'POST':
        form = RoleForm(request.POST, instance=role)
        if form.is_valid():
            form.save()
            messages.success(request, f'Role "{role.name}" mis a jour.')
            return redirect('user:roles_liste')
    else:
        form = RoleForm(instance=role)
    return render(request, 'user/role_form.html', {
        'form': form, 'titre': f'Modifier le role "{role.name}"', 'active_admin_tab': 'roles',
    })


@privilege_required(privileges.GERER_ROLES)
def role_supprimer(request, pk):
    role = get_object_or_404(Role, pk=pk)
    nb_utilisateurs = role.users.count()
    if request.method == 'POST':
        if nb_utilisateurs:
            messages.error(
                request,
                f'Impossible de supprimer le role "{role.name}" : encore assigne a {nb_utilisateurs} '
                'utilisateur(s).',
            )
        else:
            role.delete()
            messages.success(request, f'Role "{role.name}" supprime.')
        return redirect('user:roles_liste')
    return render(request, 'user/role_confirm_delete.html', {
        'role': role, 'nb_utilisateurs': nb_utilisateurs, 'active_admin_tab': 'roles',
    })


@privilege_required(privileges.GERER_UTILISATEURS)
def utilisateurs_liste(request):
    utilisateurs = User.objects.prefetch_related('roles').order_by('username')
    return render(request, 'user/utilisateurs_liste.html', {
        'utilisateurs': utilisateurs, 'active_admin_tab': 'utilisateurs',
    })


@privilege_required(privileges.GERER_UTILISATEURS)
def utilisateur_roles(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = AssignerRolesForm(request.POST)
        if form.is_valid():
            utilisateur.roles.set(form.cleaned_data['roles'])
            messages.success(request, f'Roles de {utilisateur} mis a jour.')
            return redirect('user:utilisateurs_liste')
    else:
        form = AssignerRolesForm(initial={'roles': utilisateur.roles.all()})
    return render(request, 'user/utilisateur_roles_form.html', {
        'form': form, 'utilisateur': utilisateur, 'active_admin_tab': 'utilisateurs',
    })


@privilege_required(privileges.GERER_UTILISATEURS)
def utilisateur_creer(request):
    if request.method == 'POST':
        form = UtilisateurCreationForm(request.POST)
        if form.is_valid():
            utilisateur = form.save(commit=False)
            utilisateur.is_active = True
            utilisateur.is_email_verified = True
            utilisateur.save()
            utilisateur.roles.set(form.cleaned_data['roles'])
            messages.success(request, f'Utilisateur "{utilisateur.username}" cree.')
            return redirect('user:utilisateurs_liste')
    else:
        form = UtilisateurCreationForm()
    return render(request, 'user/utilisateur_form.html', {'form': form, 'active_admin_tab': 'utilisateurs'})


@privilege_required(privileges.GERER_UTILISATEURS)
def utilisateur_toggle_actif(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        if utilisateur == request.user:
            messages.error(request, 'Vous ne pouvez pas activer/desactiver votre propre compte.')
        else:
            utilisateur.is_active = not utilisateur.is_active
            utilisateur.save(update_fields=['is_active'])
            etat = 'active' if utilisateur.is_active else 'desactive'
            messages.success(request, f'Compte "{utilisateur.username}" {etat}.')
    return redirect('user:utilisateurs_liste')


@privilege_required(privileges.GERER_UTILISATEURS)
def utilisateur_changer_mot_de_passe(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = DefinirMotDePasseForm(utilisateur, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Mot de passe de "{utilisateur.username}" mis a jour.')
            return redirect('user:utilisateurs_liste')
    else:
        form = DefinirMotDePasseForm(utilisateur)
    return render(request, 'user/utilisateur_password_form.html', {
        'form': form, 'utilisateur': utilisateur, 'active_admin_tab': 'utilisateurs',
    })
