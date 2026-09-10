"""Actions de traitement sur un Ecart : commentaire, changement de statut, piece jointe.

Chaque action cree une entree EcartHistorique (qui, quand, quelle action), cf. CLAUDE.md - Sprint 4.
"""

from .models import EcartHistorique


def ajouter_commentaire(ecart, auteur, texte):
    return EcartHistorique.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistorique.Action.COMMENTAIRE, commentaire=texte,
    )


def changer_statut(ecart, auteur, nouveau_statut):
    """Met a jour le statut de l'ecart. Ne cree pas d'entree si le statut est inchange."""
    if nouveau_statut == ecart.statut:
        return None

    ancien_statut = ecart.statut
    ecart.statut = nouveau_statut
    ecart.save(update_fields=['statut'])
    return EcartHistorique.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistorique.Action.CHANGEMENT_STATUT,
        ancien_statut=ancien_statut, nouveau_statut=nouveau_statut,
    )


def ajouter_piece_jointe(ecart, auteur, fichier, commentaire=''):
    return EcartHistorique.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistorique.Action.PIECE_JOINTE,
        fichier=fichier, commentaire=commentaire,
    )


def enregistrer_ticket_aspekt(ecart, auteur, reference):
    """Trace la creation (manuelle, hors de cette appli) d'un ticket Aspekt de regularisation."""
    return EcartHistorique.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistorique.Action.TICKET_ASPEKT,
        reference_externe=reference,
    )


def confirmer_rollback(ecart, auteur, reference=''):
    """Trace la confirmation (manuelle, hors de cette appli) d'un rollback effectue cote MVOLA."""
    return EcartHistorique.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistorique.Action.ROLLBACK_CONFIRME,
        reference_externe=reference,
    )
