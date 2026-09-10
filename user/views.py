from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.generic import FormView

from .forms import RegistrationForm
from .models import User
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
