from django.db import models

from transactions.models import ResultatRapprochement


class Ecart(models.Model):
    """Genere automatiquement a partir des lignes ORPHELINE_* d'un rapprochement.

    Cf. CLAUDE.md - Decisions prises / Sprint 2. Le suivi de regularisation (statut, qui/quand,
    pieces jointes, commentaires) sera construit sur ce modele au Sprint 4.
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
