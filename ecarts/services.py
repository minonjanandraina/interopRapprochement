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
