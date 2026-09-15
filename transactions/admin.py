from django.contrib import admin

from .models import (
    ImportFichierMvola,
    ImportFichierOM,
    ImportRequeteOM,
    ImportRequetePamf,
    Rapprochement,
    RapprochementOM,
    ResultatRapprochement,
    ResultatRapprochementOM,
    TransactionMvola,
    TransactionOM,
    TransactionPamf,
    TransactionPamfOM,
)


@admin.register(ImportFichierMvola)
class ImportFichierMvolaAdmin(admin.ModelAdmin):
    list_display = ('nom_original', 'date_fichier', 'statut', 'nb_lignes_lues', 'nb_lignes_inserees',
                     'nb_doublons', 'nb_erreurs', 'importe_par', 'importe_le')
    list_filter = ('statut', 'date_fichier')


@admin.register(TransactionMvola)
class TransactionMvolaAdmin(admin.ModelAdmin):
    list_display = ('transid_mvola', 'date_trans', 'msisdn', 'nom', 'amount', 'type_operation', 'state')
    list_filter = ('type_operation', 'state')
    search_fields = ('transid_mvola', 'msisdn', 'nom', 'origftid')
    date_hierarchy = 'date_trans'


@admin.register(ImportRequetePamf)
class ImportRequetePamfAdmin(admin.ModelAdmin):
    list_display = ('date_requete', 'statut', 'nb_lignes', 'nb_doublons', 'executee_par', 'executee_le')
    list_filter = ('statut', 'date_requete')


@admin.register(TransactionPamf)
class TransactionPamfAdmin(admin.ModelAdmin):
    list_display = ('transid_mvola', 'posting_date', 'r_autotransaction_id', 'time')
    search_fields = ('transid_mvola', 'r_autotransaction_id')
    date_hierarchy = 'posting_date'


@admin.register(Rapprochement)
class RapprochementAdmin(admin.ModelAdmin):
    list_display = ('date', 'statut', 'nb_mvola', 'nb_pamf', 'nb_success',
                     'nb_orphelines_mvola', 'nb_orphelines_pamf', 'lance_par', 'execute_le')
    list_filter = ('statut',)
    date_hierarchy = 'date'


@admin.register(ResultatRapprochement)
class ResultatRapprochementAdmin(admin.ModelAdmin):
    list_display = ('transid_mvola', 'rapprochement', 'statut')
    list_filter = ('statut',)
    search_fields = ('transid_mvola',)


@admin.register(ImportFichierOM)
class ImportFichierOMAdmin(admin.ModelAdmin):
    list_display = ('nom_original', 'date_fichier', 'statut', 'nb_lignes_lues', 'nb_lignes_inserees',
                     'nb_doublons', 'nb_hors_succes', 'nb_erreurs', 'importe_par', 'importe_le')
    list_filter = ('statut', 'date_fichier')


@admin.register(TransactionOM)
class TransactionOMAdmin(admin.ModelAdmin):
    list_display = ('transid_om', 'date_trans', 'msisdn', 'montant', 'statut')
    list_filter = ('statut',)
    search_fields = ('transid_om', 'msisdn')
    date_hierarchy = 'date_trans'


@admin.register(ImportRequeteOM)
class ImportRequeteOMAdmin(admin.ModelAdmin):
    list_display = ('date_requete', 'statut', 'nb_lignes', 'nb_doublons', 'executee_par', 'executee_le')
    list_filter = ('statut', 'date_requete')


@admin.register(TransactionPamfOM)
class TransactionPamfOMAdmin(admin.ModelAdmin):
    list_display = ('transid_om', 'posting_date', 'r_autotransaction_id', 'time', 'montant', 'is_success')
    search_fields = ('transid_om', 'r_autotransaction_id')
    date_hierarchy = 'posting_date'


@admin.register(RapprochementOM)
class RapprochementOMAdmin(admin.ModelAdmin):
    list_display = ('date', 'statut', 'nb_om', 'nb_pamf', 'nb_success',
                     'nb_orphelines_om', 'nb_orphelines_pamf', 'lance_par', 'execute_le')
    list_filter = ('statut',)
    date_hierarchy = 'date'


@admin.register(ResultatRapprochementOM)
class ResultatRapprochementOMAdmin(admin.ModelAdmin):
    list_display = ('transid_om', 'rapprochement', 'statut')
    list_filter = ('statut',)
    search_fields = ('transid_om',)
