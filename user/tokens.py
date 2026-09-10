from django.contrib.auth.tokens import PasswordResetTokenGenerator


class AccountActivationTokenGenerator(PasswordResetTokenGenerator):
    """Genere un token invalide des que is_email_verified passe a True."""

    def _make_hash_value(self, user, timestamp):
        return f'{user.pk}{timestamp}{user.is_email_verified}'


account_activation_token = AccountActivationTokenGenerator()
