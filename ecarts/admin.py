from django.contrib import admin

from .models import Ecart, EcartHistorique


@admin.register(Ecart)
class EcartAdmin(admin.ModelAdmin):
    list_display = ('transid_mvola', 'type_ecart', 'date_transaction', 'statut', 'detecte_le')
    list_filter = ('type_ecart', 'statut', 'date_transaction')
    search_fields = ('transid_mvola',)
    date_hierarchy = 'date_transaction'


@admin.register(EcartHistorique)
class EcartHistoriqueAdmin(admin.ModelAdmin):
    list_display = ('ecart', 'action', 'auteur', 'horodatage')
    list_filter = ('action',)
