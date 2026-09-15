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


def resoudre_doublon_pamf(ecart, auteur, transaction_pamf):
    """Enregistre le choix de l'agent parmi plusieurs postings PAMF candidats pour ce transid
    (cf. CLAUDE.md - Decisions prises, paiement marchand scinde sur plusieurs prets cote CBS).

    Ne recalcule pas le statut de l'ecart/ResultatRapprochement : DOUBLON_PAMF reste un marqueur
    historique de l'ambiguite initiale, comme TICKET_ASPEKT/ROLLBACK_CONFIRME ne changent pas non
    plus le statut de suivi automatiquement.
    """
    resultat = ecart.resultat
    resultat.transaction_pamf = transaction_pamf
    resultat.save(update_fields=['transaction_pamf'])
    statut_cbs = 'Succes' if transaction_pamf.is_success else 'Echec'
    return EcartHistorique.objects.create(
        ecart=ecart, auteur=auteur, action=EcartHistorique.Action.RESOLUTION_DOUBLON,
        reference_externe=transaction_pamf.r_autotransaction_id,
        commentaire=f'Posting choisi comme reference : rAutotransactionID={transaction_pamf.r_autotransaction_id}, statut CBS={statut_cbs}.',
    )
