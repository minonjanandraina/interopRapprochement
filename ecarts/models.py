from django.conf import settings
from django.db import models

from transactions.models import ResultatRapprochement, ResultatRapprochementOM


class Ecart(models.Model):
    """Genere automatiquement a partir des lignes ORPHELINE_* d'un rapprochement.

    Cf. CLAUDE.md - Decisions prises / Sprint 2. Le suivi de regularisation (statut, qui/quand,
    pieces jointes, commentaires) est construit sur ce modele au Sprint 4 (cf. EcartHistorique).
    """

    class TypeEcart(models.TextChoices):
        ORPHELINE_MVOLA = 'ORPHELINE_MVOLA', 'Orpheline MVOLA'
        ORPHELINE_PAMF = 'ORPHELINE_PAMF', 'Orpheline PAMF'
        DOUBLON_PAMF = 'DOUBLON_PAMF', 'Doublon PAMF (postings multiples)'
        TRANSACTION_REJOUEE = 'TRANSACTION_REJOUEE', 'Transaction rejouee'

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

    @property
    def action_recommandee(self):
        """Delegue a ResultatRapprochement.action_recommandee (cf. CLAUDE.md - rollback MVOLA
        vs ticket Aspekt, deduit du statut PAMF is_success)."""
        return self.resultat.action_recommandee

    @property
    def montant(self):
        """Montant de la transaction MVOLA associee (source 1, cf. CLAUDE.md).

        La requete CBS ne remonte pas de montant cote PAMF : pour une ORPHELINE_PAMF
        (transaction_mvola absente), aucun montant n'est disponible dans nos donnees.
        """
        transaction_mvola = self.resultat.transaction_mvola
        return transaction_mvola.amount if transaction_mvola else None


class EcartHistorique(models.Model):
    """Journal des actions de traitement sur un ecart : qui, quand, quelle action."""

    class Action(models.TextChoices):
        COMMENTAIRE = 'COMMENTAIRE', 'Commentaire'
        CHANGEMENT_STATUT = 'CHANGEMENT_STATUT', 'Changement de statut'
        PIECE_JOINTE = 'PIECE_JOINTE', 'Piece jointe'
        TICKET_ASPEKT = 'TICKET_ASPEKT', 'Ticket Aspekt enregistre'
        ROLLBACK_CONFIRME = 'ROLLBACK_CONFIRME', 'Rollback MVOLA confirme'
        RESOLUTION_DOUBLON = 'RESOLUTION_DOUBLON', 'Doublon PAMF resolu'

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
    reference_externe = models.CharField(
        max_length=100, blank=True,
        help_text='Reference du ticket Aspekt, ou reference/commentaire de la confirmation de rollback.',
    )

    class Meta:
        ordering = ['-horodatage']

    def __str__(self):
        return f'{self.get_action_display()} sur ecart #{self.ecart_id} par {self.auteur}'


# --- Orange Money (OM) ------------------------------------------------------------------------
# Miroir de Ecart/EcartHistorique (MVOLA) ci-dessus - cf. CLAUDE.md, Decisions prises
# (duplication OM plutot que generalisation).


class EcartOM(models.Model):
    """Genere automatiquement a partir des lignes ORPHELINE_* d'un rapprochement Orange Money."""

    class TypeEcart(models.TextChoices):
        ORPHELINE_OM = 'ORPHELINE_OM', 'Orpheline Orange Money'
        ORPHELINE_PAMF = 'ORPHELINE_PAMF', 'Orpheline PAMF'
        DOUBLON_PAMF = 'DOUBLON_PAMF', 'Doublon PAMF (postings multiples)'
        TRANSACTION_REJOUEE = 'TRANSACTION_REJOUEE', 'Transaction rejouee'

    class Statut(models.TextChoices):
        DETECTE = 'DETECTE', 'Detecte'
        EN_COURS = 'EN_COURS', 'En cours de traitement'
        REGULARISE = 'REGULARISE', 'Regularise'

    resultat = models.OneToOneField(ResultatRapprochementOM, on_delete=models.CASCADE, related_name='ecart')
    transid_om = models.CharField(max_length=50, db_index=True)
    type_ecart = models.CharField(max_length=20, choices=TypeEcart.choices)
    date_transaction = models.DateField()
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.DETECTE)
    detecte_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-detecte_le']

    def __str__(self):
        return f'Ecart OM {self.transid_om} ({self.type_ecart})'

    @property
    def action_recommandee(self):
        """Delegue a ResultatRapprochementOM.action_recommandee."""
        return self.resultat.action_recommandee

    @property
    def montant(self):
        """Montant de la transaction Orange Money associee (source 1, cf. CLAUDE.md).

        La requete CBS ne remonte pas de montant cote PAMF : pour une ORPHELINE_PAMF
        (transaction_om absente), aucun montant n'est disponible dans nos donnees.
        """
        transaction_om = self.resultat.transaction_om
        return transaction_om.montant if transaction_om else None


class EcartHistoriqueOM(models.Model):
    """Journal des actions de traitement sur un EcartOM : qui, quand, quelle action."""

    class Action(models.TextChoices):
        COMMENTAIRE = 'COMMENTAIRE', 'Commentaire'
        CHANGEMENT_STATUT = 'CHANGEMENT_STATUT', 'Changement de statut'
        PIECE_JOINTE = 'PIECE_JOINTE', 'Piece jointe'
        TICKET_ASPEKT = 'TICKET_ASPEKT', 'Ticket Aspekt enregistre'
        ROLLBACK_CONFIRME = 'ROLLBACK_CONFIRME', 'Rollback Orange Money confirme'
        RESOLUTION_DOUBLON = 'RESOLUTION_DOUBLON', 'Doublon PAMF resolu'

    ecart = models.ForeignKey(EcartOM, on_delete=models.CASCADE, related_name='historique')
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='actions_ecarts_om',
    )
    horodatage = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    commentaire = models.TextField(blank=True)
    ancien_statut = models.CharField(max_length=15, blank=True)
    nouveau_statut = models.CharField(max_length=15, blank=True)
    fichier = models.FileField(upload_to='ecarts/pieces_jointes_om/%Y/%m/', blank=True, null=True)
    reference_externe = models.CharField(
        max_length=100, blank=True,
        help_text='Reference du ticket Aspekt, ou reference/commentaire de la confirmation de rollback.',
    )

    class Meta:
        ordering = ['-horodatage']

    def __str__(self):
        return f'{self.get_action_display()} sur ecart OM #{self.ecart_id} par {self.auteur}'
