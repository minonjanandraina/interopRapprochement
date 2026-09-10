from django.conf import settings
from django.db import models

from transactions.models import ResultatRapprochement


class Ecart(models.Model):
    """Genere automatiquement a partir des lignes ORPHELINE_* d'un rapprochement.

    Cf. CLAUDE.md - Decisions prises / Sprint 2. Le suivi de regularisation (statut, qui/quand,
    pieces jointes, commentaires) est construit sur ce modele au Sprint 4 (cf. EcartHistorique).
    """

    class TypeEcart(models.TextChoices):
        ORPHELINE_MVOLA = 'ORPHELINE_MVOLA', 'Orpheline MVOLA'
        ORPHELINE_PAMF = 'ORPHELINE_PAMF', 'Orpheline PAMF'

    class Statut(models.TextChoices):
        DETECTE = 'DETECTE', 'Detecte'
        EN_COURS = 'EN_COURS', 'En cours de traitement'
        REGULARISE = 'REGULARISE', 'Regularise'

    resultat = models.OneToOneField(ResultatRapprochement, on_delete=models.CASCADE, related_name='ecart')
    transid_mvola = models.CharField(max_length=50, db_index=True)
    type_ecart = models.CharField(max_length=20, choices=TypeEcart.choices)
    date_transaction = models.DateField()
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.DETECTE)
    detecte_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-detecte_le']

    def __str__(self):
        return f'Ecart {self.transid_mvola} ({self.type_ecart})'


class EcartHistorique(models.Model):
    """Journal des actions de traitement sur un ecart : qui, quand, quelle action."""

    class Action(models.TextChoices):
        COMMENTAIRE = 'COMMENTAIRE', 'Commentaire'
        CHANGEMENT_STATUT = 'CHANGEMENT_STATUT', 'Changement de statut'
        PIECE_JOINTE = 'PIECE_JOINTE', 'Piece jointe'

    ecart = models.ForeignKey(Ecart, on_delete=models.CASCADE, related_name='historique')
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='actions_ecarts',
    )
    horodatage = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    commentaire = models.TextField(blank=True)
    ancien_statut = models.CharField(max_length=15, blank=True)
    nouveau_statut = models.CharField(max_length=15, blank=True)
    fichier = models.FileField(upload_to='ecarts/pieces_jointes/%Y/%m/', blank=True, null=True)

    class Meta:
        ordering = ['-horodatage']

    def __str__(self):
        return f'{self.get_action_display()} sur ecart #{self.ecart_id} par {self.auteur}'
