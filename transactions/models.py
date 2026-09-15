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
    """Une ligne issue de la requete CBS (source 2, cf. CLAUDE.md).

    transid_mvola n'est PAS unique : un paiement marchand peut etre scinde cote CBS sur plusieurs
    prets (plusieurs mcTransaction/rAutotransactionID pour un meme RequestID/apiLogID) - constate
    sur donnees reelles (meme phenomene qu'Orange Money, cf. CLAUDE.md - Decisions prises).
    """

    r_autotransaction_id = models.CharField('rAutotransactionID', max_length=50)
    posting_date = models.DateField()
    time = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    transid_mvola = models.CharField('TRANSID_MVOLA', max_length=50, db_index=True)
    response_body = models.TextField(blank=True)
    is_success = models.BooleanField(
        'is_sucess', default=True,
        help_text="Status CBS = 3 (poste/valide). False = transaction presente mais en echec cote PAMF.",
    )
    import_requete = models.ForeignKey(
        ImportRequetePamf, on_delete=models.PROTECT, related_name='transactions',
    )

    class Meta:
        ordering = ['-posting_date']
        indexes = [models.Index(fields=['posting_date'])]
        constraints = [
            models.UniqueConstraint(
                fields=['transid_mvola', 'r_autotransaction_id'], name='unique_pamf_transid_rautotransactionid',
            ),
        ]

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
    nb_doublons_pamf = models.PositiveIntegerField(
        default=0, help_text="Transactions avec plusieurs postings PAMF, a resoudre manuellement.",
    )
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
        DOUBLON_PAMF = 'DOUBLON_PAMF', 'Doublon PAMF (postings multiples)'

    class ActionRecommandee(models.TextChoices):
        ROLLBACK_MVOLA = 'ROLLBACK_MVOLA', 'Rollback cote MVOLA'
        TICKET_ASPEKT = 'TICKET_ASPEKT', 'Creation ticket Aspekt'
        CHOISIR_POSTING = 'CHOISIR_POSTING', 'Choisir le posting PAMF de reference'

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

    @property
    def action_recommandee(self):
        """Action recommandee, cf. CLAUDE.md :

        - DOUBLON_PAMF (plusieurs postings CBS pour ce transid) -> choisir le posting de
          reference (CHOISIR_POSTING) tant qu'aucun n'a ete choisi, sinon plus d'action a faire.
        - orpheline MVOLA avec une ligne PAMF en echec (is_success=False) -> la requete a bien
          atteint Aspekt/CBS mais son traitement a echoue -> Aspekt peut corriger -> ticket Aspekt
        - orpheline MVOLA sans aucune ligne PAMF -> la requete n'a meme pas atteint Aspekt -> rien
          a corriger de son cote -> rollback recommande cote MVOLA (credit retour du wallet)
        """
        if self.statut == self.Statut.DOUBLON_PAMF:
            return None if self.transaction_pamf_id else self.ActionRecommandee.CHOISIR_POSTING
        if self.statut != self.Statut.ORPHELINE_MVOLA:
            return None
        if self.transaction_pamf is not None and not self.transaction_pamf.is_success:
            return self.ActionRecommandee.TICKET_ASPEKT
        return self.ActionRecommandee.ROLLBACK_MVOLA


# --- Orange Money (OM) ------------------------------------------------------------------------
# Duplication volontaire des modeles MVOLA ci-dessus plutot qu'une generalisation : cf. CLAUDE.md
# - Decisions prises (duplication OM). Meme pipeline (import fichier -> requete CBS -> matching
# bulk -> Ecart), source 1 differente (XLS Orange Money au lieu du CSV MVOLA, cf. xls_om.py) et
# cle de jointure differente (TRANSID_ORANGE_MONEY / transid_om).


class ImportFichierOM(models.Model):
    """Trace chaque depot manuel d'un fichier XLS Orange Money
    (Daily-ChannelUserTransactionReport-<compte>-YYYYMMDD.xls)."""

    class Statut(models.TextChoices):
        SUCCES = 'SUCCES', 'Succes'
        ECHEC = 'ECHEC', 'Echec'

    fichier = models.FileField(upload_to='imports/om/%Y/%m/')
    nom_original = models.CharField(max_length=255)
    date_fichier = models.DateField('date du fichier')
    importe_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='imports_om',
    )
    importe_le = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=10, choices=Statut.choices)
    nb_lignes_lues = models.PositiveIntegerField(default=0)
    nb_lignes_inserees = models.PositiveIntegerField(default=0)
    nb_doublons = models.PositiveIntegerField(default=0)
    nb_hors_succes = models.PositiveIntegerField(
        default=0, help_text="Lignes ignorees car Statut != Succes (cf. CLAUDE.md).",
    )
    nb_erreurs = models.PositiveIntegerField(default=0)
    message_erreur = models.TextField(blank=True)

    class Meta:
        ordering = ['-importe_le']

    def __str__(self):
        return f'{self.nom_original} ({self.date_fichier}) - {self.statut}'


class TransactionOM(models.Model):
    """Une ligne (Statut = Succes) du relevé XLS Orange Money (source 1, cf. CLAUDE.md)."""

    numero_ligne = models.PositiveIntegerField('N (relevé OM)')
    date_trans = models.DateTimeField()
    transid_om = models.CharField('TRANSID_ORANGE_MONEY', max_length=50, unique=True, db_index=True)
    service = models.CharField(max_length=50, blank=True)
    paiement = models.CharField(max_length=50, blank=True)
    statut = models.CharField(max_length=20)
    mode = models.CharField(max_length=30, blank=True)
    compte_technique = models.CharField(max_length=30, blank=True)
    wallet_agent = models.CharField(max_length=30, blank=True)
    pseudo = models.CharField(max_length=50, blank=True)
    msisdn = models.CharField(max_length=20)
    wallet_correspondant = models.CharField(max_length=30, blank=True)
    debit = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    montant = models.DecimalField(max_digits=18, decimal_places=2, help_text='Colonne Credit (MGA).')
    commissions = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    import_fichier = models.ForeignKey(
        ImportFichierOM, on_delete=models.PROTECT, related_name='transactions',
    )

    class Meta:
        ordering = ['-date_trans']
        indexes = [models.Index(fields=['date_trans'])]

    def __str__(self):
        return self.transid_om


class ImportRequeteOM(models.Model):
    """Trace chaque interrogation de la base CBS (marchand Orange Money) pour une date donnee."""

    class Statut(models.TextChoices):
        SUCCES = 'SUCCES', 'Succes'
        ECHEC = 'ECHEC', 'Echec'

    date_requete = models.DateField('date interrogee (postingDate)')
    executee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='imports_pamf_om',
    )
    executee_le = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=10, choices=Statut.choices)
    nb_lignes = models.PositiveIntegerField(default=0)
    nb_doublons = models.PositiveIntegerField(default=0)
    message_erreur = models.TextField(blank=True)

    class Meta:
        ordering = ['-executee_le']

    def __str__(self):
        return f'CBS OM {self.date_requete} - {self.statut}'


class TransactionPamfOM(models.Model):
    """Une ligne issue de la requete CBS Orange Money (rMerchantID=9, source 2, cf. CLAUDE.md).

    transid_om n'est PAS unique : un doublon PAMF (plusieurs mcTransaction/rAutotransactionID
    pour un meme RequestID) reste possible pour les apiServiceId 302/700 et doit etre resolu
    manuellement (cf. CLAUDE.md - DOUBLON_PAMF). Le cas apiServiceId=303 (repaymentByAlias -
    remboursement sans montant precise, scinde par le CBS sur les prets actifs echus) est en
    revanche deja agrege en une seule ligne par la requete SQL elle-meme (SUM des montants,
    succes ssi tous les postings ont reussi) - constate sur donnees reelles (2026-09-08).
    """

    r_autotransaction_id = models.CharField('rAutotransactionID', max_length=50)
    posting_date = models.DateField()
    time = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    transid_om = models.CharField('TRANSID_ORANGE_MONEY', max_length=50, db_index=True)
    response_body = models.TextField(blank=True)
    montant = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
        help_text="Montant CBS (AmountCRY), somme des postings pour un remboursement scinde (apiServiceId=303).",
    )
    is_success = models.BooleanField(
        'is_sucess', default=True,
        help_text="Status CBS = 3 (poste/valide). False = transaction presente mais en echec cote PAMF.",
    )
    import_requete = models.ForeignKey(
        ImportRequeteOM, on_delete=models.PROTECT, related_name='transactions',
    )

    class Meta:
        ordering = ['-posting_date']
        indexes = [models.Index(fields=['posting_date'])]
        constraints = [
            models.UniqueConstraint(
                fields=['transid_om', 'r_autotransaction_id'], name='unique_pamfom_transid_rautotransactionid',
            ),
        ]

    def __str__(self):
        return self.transid_om


class RapprochementOM(models.Model):
    """Un process de reconciliation Orange Money / PAMF pour une date donnee.

    Miroir de Rapprochement (MVOLA) - declenche manuellement par date, un seul enregistrement par
    date, relancer recalcule entierement (cf. CLAUDE.md - Decisions prises).
    """

    class Statut(models.TextChoices):
        EN_COURS = 'EN_COURS', 'En cours'
        TERMINE = 'TERMINE', 'Termine'
        ECHEC = 'ECHEC', 'Echec'

    date = models.DateField(unique=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.EN_COURS)
    lance_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='rapprochements_om',
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    execute_le = models.DateTimeField(auto_now=True)
    nb_om = models.PositiveIntegerField(default=0)
    nb_pamf = models.PositiveIntegerField(default=0)
    nb_success = models.PositiveIntegerField(default=0)
    nb_orphelines_om = models.PositiveIntegerField(default=0)
    nb_orphelines_pamf = models.PositiveIntegerField(default=0)
    nb_doublons_pamf = models.PositiveIntegerField(
        default=0, help_text="Transactions avec plusieurs postings PAMF, a resoudre manuellement.",
    )
    message_erreur = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'Rapprochement OM {self.date} ({self.statut})'


class ResultatRapprochementOM(models.Model):
    """Statut d'une transaction (identifiee par TRANSID_ORANGE_MONEY) pour un rapprochement OM."""

    class Statut(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Rapprochee'
        ORPHELINE_OM = 'ORPHELINE_OM', 'Orpheline Orange Money'
        ORPHELINE_PAMF = 'ORPHELINE_PAMF', 'Orpheline PAMF'
        DOUBLON_PAMF = 'DOUBLON_PAMF', 'Doublon PAMF (postings multiples)'

    class ActionRecommandee(models.TextChoices):
        ROLLBACK_OM = 'ROLLBACK_OM', 'Rollback cote Orange Money'
        TICKET_ASPEKT = 'TICKET_ASPEKT', 'Creation ticket Aspekt'
        CHOISIR_POSTING = 'CHOISIR_POSTING', 'Choisir le posting PAMF de reference'

    rapprochement = models.ForeignKey(RapprochementOM, on_delete=models.CASCADE, related_name='resultats')
    transid_om = models.CharField(max_length=50, db_index=True)
    statut = models.CharField(max_length=20, choices=Statut.choices)
    transaction_om = models.ForeignKey(
        TransactionOM, null=True, blank=True, on_delete=models.SET_NULL, related_name='resultats',
    )
    transaction_pamf = models.ForeignKey(
        TransactionPamfOM, null=True, blank=True, on_delete=models.SET_NULL, related_name='resultats',
    )

    class Meta:
        ordering = ['transid_om']
        constraints = [
            models.UniqueConstraint(fields=['rapprochement', 'transid_om'], name='unique_resultat_om_par_transid'),
        ]
        indexes = [models.Index(fields=['statut'])]

    def __str__(self):
        return f'{self.transid_om} - {self.statut}'

    @property
    def action_recommandee(self):
        """Cf. ResultatRapprochement.action_recommandee (MVOLA) - meme logique, appliquee a une
        orpheline Orange Money."""
        if self.statut == self.Statut.DOUBLON_PAMF:
            return None if self.transaction_pamf_id else self.ActionRecommandee.CHOISIR_POSTING
        if self.statut != self.Statut.ORPHELINE_OM:
            return None
        if self.transaction_pamf is not None and not self.transaction_pamf.is_success:
            return self.ActionRecommandee.TICKET_ASPEKT
        return self.ActionRecommandee.ROLLBACK_OM
