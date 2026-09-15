"""Notification email lors de la detection de nouveaux ecarts apres un rapprochement.

Cf. CLAUDE.md - Sprint 5. Envoi via le serveur SMTP interne PAMF (section "Serveur mail").
Un echec d'envoi ne doit jamais faire echouer le rapprochement lui-meme : les erreurs sont
journalisees plutot que propagees.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Q
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _destinataires():
    """Utilisateurs actifs a notifier : email verifie (inscription standard), ou staff/superuser
    (comptes crees via `createsuperuser`/l'admin, qui ne passent pas par l'activation email)."""
    User = get_user_model()
    return list(
        User.objects.filter(is_active=True)
        .filter(Q(is_email_verified=True) | Q(is_staff=True))
        .exclude(email='')
        .values_list('email', flat=True)
    )


def notifier_nouveaux_ecarts(rapprochement, ecarts):
    """Envoie un email aux utilisateurs actifs/verifies listant les nouveaux ecarts detectes."""
    if not ecarts:
        return

    destinataires = _destinataires()
    if not destinataires:
        return

    message = render_to_string('ecarts/emails/nouveaux_ecarts.txt', {
        'rapprochement': rapprochement,
        'ecarts': ecarts,
        'site_base_url': settings.SITE_BASE_URL,
    })

    try:
        send_mail(
            subject=f"[interopRapprochement] {len(ecarts)} nouvel(le)s ecart(s) detecte(s) - {rapprochement.date}",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=destinataires,
        )
    except Exception:
        logger.exception(
            "Echec de l'envoi de la notification de nouveaux ecarts pour le rapprochement du %s",
            rapprochement.date,
        )


def notifier_nouveaux_ecarts_om(rapprochement, ecarts):
    """Miroir de notifier_nouveaux_ecarts (MVOLA) pour le service Orange Money."""
    if not ecarts:
        return

    destinataires = _destinataires()
    if not destinataires:
        return

    message = render_to_string('ecarts/emails/nouveaux_ecarts_om.txt', {
        'rapprochement': rapprochement,
        'ecarts': ecarts,
        'site_base_url': settings.SITE_BASE_URL,
    })

    try:
        send_mail(
            subject=f"[interopRapprochement] {len(ecarts)} nouvel(le)s ecart(s) Orange Money detecte(s) - {rapprochement.date}",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=destinataires,
        )
    except Exception:
        logger.exception(
            "Echec de l'envoi de la notification de nouveaux ecarts Orange Money pour le rapprochement du %s",
            rapprochement.date,
        )
