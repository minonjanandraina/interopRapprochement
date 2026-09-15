"""Actions de traitement sur un EcartOM : commentaire, changement de statut, piece jointe.

Miroir de services.py (MVOLA) - cree des EcartHistoriqueOM au lieu de EcartHistorique, cf.
CLAUDE.md - Decisions prises (duplication OM).
"""

from .models import EcartHistoriqueOM


def ajouter_commentaire(ecart, auteur, texte):
    return EcartHistoriqueOM.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistoriqueOM.Action.COMMENTAIRE, commentaire=texte,
    )


def changer_statut(ecart, auteur, nouveau_statut):
    """Met a jour le statut de l'ecart. Ne cree pas d'entree si le statut est inchange."""
    if nouveau_statut == ecart.statut:
        return None

    ancien_statut = ecart.statut
    ecart.statut = nouveau_statut
    ecart.save(update_fields=['statut'])
    return EcartHistoriqueOM.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistoriqueOM.Action.CHANGEMENT_STATUT,
        ancien_statut=ancien_statut, nouveau_statut=nouveau_statut,
    )


def ajouter_piece_jointe(ecart, auteur, fichier, commentaire=''):
    return EcartHistoriqueOM.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistoriqueOM.Action.PIECE_JOINTE,
        fichier=fichier, commentaire=commentaire,
    )


def enregistrer_ticket_aspekt(ecart, auteur, reference):
    """Trace la creation (manuelle, hors de cette appli) d'un ticket Aspekt de regularisation."""
    return EcartHistoriqueOM.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistoriqueOM.Action.TICKET_ASPEKT,
        reference_externe=reference,
    )


def confirmer_rollback(ecart, auteur, reference=''):
    """Trace la confirmation (manuelle, hors de cette appli) d'un rollback effectue cote Orange
    Money."""
    return EcartHistoriqueOM.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistoriqueOM.Action.ROLLBACK_CONFIRME,
        reference_externe=reference,
    )


def resoudre_doublon_pamf(ecart, auteur, transaction_pamf):
    """Cf. ecarts.services.resoudre_doublon_pamf (MVOLA) - meme mecanisme pour Orange Money."""
    resultat = ecart.resultat
    resultat.transaction_pamf = transaction_pamf
    resultat.save(update_fields=['transaction_pamf'])
    statut_cbs = 'Succes' if transaction_pamf.is_success else 'Echec'
    return EcartHistoriqueOM.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistoriqueOM.Action.RESOLUTION_DOUBLON,
        reference_externe=transaction_pamf.r_autotransaction_id,
        commentaire=f'Posting choisi comme reference : rAutotransactionID={transaction_pamf.r_autotransaction_id}, statut CBS={statut_cbs}.',
    )
