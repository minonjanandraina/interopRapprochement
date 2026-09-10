from django.conf import settings
from django.db import models


class ImportFichierMvola(models.Model):
    """Trace chaque depot manuel d'un fichier CSV MVOLA (YYYY-MM-DD_reporting_PAMF.csv)."""

    class Statut(models.TextChoices):
        SUCCES = 'SUCCES', 'Succes'
        ECHEC = 'ECHEC', 'Echec'

    fichier = models.FileField(upload_to='imports/mvola/%Y/%m/')
    nom_original = models.CharField(max_length=255)
    date_fichier = models.DateField('date du fichier')
    importe_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='imports_mvola',
    )
    importe_le = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=10, choices=Statut.choices)
    nb_lignes_lues = models.PositiveIntegerField(default=0)
    nb_lignes_inserees = models.PositiveIntegerField(default=0)
    nb_doublons = models.PositiveIntegerField(default=0)
    nb_erreurs = models.PositiveIntegerField(default=0)
    message_erreur = models.TextField(blank=True)

    class Meta:
        ordering = ['-importe_le']

    def __str__(self):
        return f'{self.nom_original} ({self.date_fichier}) - {self.statut}'


class TransactionMvola(models.Model):
    """Une ligne du CSV MVOLA (source 1, cf. CLAUDE.md)."""

    date_trans = models.DateTimeField()
    transid_mvola = models.CharField('TRANSID_MVOLA', max_length=50, unique=True, db_index=True)
    state = models.CharField(max_length=30)
    msisdn = models.CharField(max_length=20)
    pivot = models.CharField(max_length=30)
    sens = models.CharField(max_length=5)
    nom = models.CharField(max_length=150)
    transid_parent = models.CharField(max_length=50, blank=True, default='0')
    trans_type = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    solde_pivot_avant = models.DecimalField(max_digits=18, decimal_places=2)
    solde_pivot_apres = models.DecimalField(max_digits=18, decimal_places=2)
    origftid = models.CharField(max_length=50, blank=True)
    type_operation = models.CharField(max_length=10)
    import_fichier = models.ForeignKey(
        ImportFichierMvola, on_delete=models.PROTECT, related_name='transactions',
    )

    class Meta:
        ordering = ['-date_trans']
        indexes = [models.Index(fields=['date_trans'])]

    def __str__(self):
        return self.transid_mvola


class ImportRequetePamf(models.Model):
    """Trace chaque interrogation de la base CBS pour une date donnee (source 2, cf. CLAUDE.md)."""

    class Statut(models.TextChoices):
        SUCCES = 'SUCCES', 'Succes'
        ECHEC = 'ECHEC', 'Echec'

    date_requete = models.DateField('date interrogee (postingDate)')
    executee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='imports_pamf',
    )
    executee_le = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=10, choices=Statut.choices)
    nb_lignes = models.PositiveIntegerField(default=0)
    nb_doublons = models.PositiveIntegerField(default=0)
    message_erreur = models.TextField(blank=True)

    class Meta:
        ordering = ['-executee_le']

    def __str__(self):
        return f'CBS {self.date_requete} - {self.statut}'


class TransactionPamf(models.Model):
    """Une ligne issue de la requete CBS (source 2, cf. CLAUDE.md)."""

    r_autotransaction_id = models.CharField('rAutotransactionID', max_length=50)
    posting_date = models.DateField()
    time = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    transid_mvola = models.CharField('TRANSID_MVOLA', max_length=50, unique=True, db_index=True)
    response_body = models.TextField(blank=True)
    import_requete = models.ForeignKey(
        ImportRequetePamf, on_delete=models.PROTECT, related_name='transactions',
    )

    class Meta:
        ordering = ['-posting_date']
        indexes = [models.Index(fields=['posting_date'])]

    def __str__(self):
        return self.transid_mvola


class Rapprochement(models.Model):
    """Un process de reconciliation MVOLA / PAMF pour une date donnee.

    Declenche manuellement par date (cf. CLAUDE.md - Decisions prises). Un seul enregistrement
    par date : relancer le rapprochement met a jour ce meme enregistrement (recalcul complet).
    """

    class Statut(models.TextChoices):
        EN_COURS = 'EN_COURS', 'En cours'
        TERMINE = 'TERMINE', 'Termine'
        ECHEC = 'ECHEC', 'Echec'

    date = models.DateField(unique=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.EN_COURS)
    lance_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='rapprochements',
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    execute_le = models.DateTimeField(auto_now=True)
    nb_mvola = models.PositiveIntegerField(default=0)
    nb_pamf = models.PositiveIntegerField(default=0)
    nb_success = models.PositiveIntegerField(default=0)
    nb_orphelines_mvola = models.PositiveIntegerField(default=0)
    nb_orphelines_pamf = models.PositiveIntegerField(default=0)
    message_erreur = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'Rapprochement {self.date} ({self.statut})'


class ResultatRapprochement(models.Model):
    """Statut d'une transaction (identifiee par TRANSID_MVOLA) pour un rapprochement donne."""

    class Statut(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Rapprochee'
        ORPHELINE_MVOLA = 'ORPHELINE_MVOLA', 'Orpheline MVOLA'
        ORPHELINE_PAMF = 'ORPHELINE_PAMF', 'Orpheline PAMF'

    rapprochement = models.ForeignKey(Rapprochement, on_delete=models.CASCADE, related_name='resultats')
    transid_mvola = models.CharField(max_length=50, db_index=True)
    statut = models.CharField(max_length=20, choices=Statut.choices)
    transaction_mvola = models.ForeignKey(
        TransactionMvola, null=True, blank=True, on_delete=models.SET_NULL, related_name='resultats',
    )
    transaction_pamf = models.ForeignKey(
        TransactionPamf, null=True, blank=True, on_delete=models.SET_NULL, related_name='resultats',
    )

    class Meta:
        ordering = ['transid_mvola']
        constraints = [
            models.UniqueConstraint(fields=['rapprochement', 'transid_mvola'], name='unique_resultat_par_transid'),
        ]
        indexes = [models.Index(fields=['statut'])]

    def __str__(self):
        return f'{self.transid_mvola} - {self.statut}'
