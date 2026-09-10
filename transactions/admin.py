from django.contrib import admin

from .models import (
    ImportFichierMvola,
    ImportRequetePamf,
    Rapprochement,
    ResultatRapprochement,
    TransactionMvola,
    TransactionPamf,
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
