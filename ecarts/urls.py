from django.urls import path

from . import views

app_name = 'ecarts'

urlpatterns = [
    path('mvola/ecarts/', views.mvola_liste, name='mvola_liste'),
    path('mvola/ecarts/export/<str:format>/', views.mvola_liste_export, name='mvola_liste_export'),
    path('mvola/ecarts/<int:pk>/', views.detail, name='detail'),
    path('mvola/ecarts/<int:pk>/commentaire/', views.ajouter_commentaire_vue, name='ajouter_commentaire'),
    path('mvola/ecarts/<int:pk>/statut/', views.changer_statut_vue, name='changer_statut'),
    path('mvola/ecarts/<int:pk>/piece-jointe/', views.ajouter_piece_jointe_vue, name='ajouter_piece_jointe'),
    path('mvola/ecarts/<int:pk>/ticket-aspekt/', views.enregistrer_ticket_aspekt_vue, name='enregistrer_ticket_aspekt'),
    path('mvola/ecarts/<int:pk>/rollback-confirme/', views.confirmer_rollback_vue, name='confirmer_rollback'),
    path('mvola/ecarts/<int:pk>/resoudre-doublon/', views.resoudre_doublon_pamf_vue, name='resoudre_doublon_pamf'),

    path('om/ecarts/', views.om_liste, name='om_liste'),
    path('om/ecarts/export/<str:format>/', views.om_liste_export, name='om_liste_export'),
    path('om/ecarts/<int:pk>/', views.om_detail, name='om_detail'),
    path('om/ecarts/<int:pk>/commentaire/', views.om_ajouter_commentaire_vue, name='om_ajouter_commentaire'),
    path('om/ecarts/<int:pk>/statut/', views.om_changer_statut_vue, name='om_changer_statut'),
    path('om/ecarts/<int:pk>/piece-jointe/', views.om_ajouter_piece_jointe_vue, name='om_ajouter_piece_jointe'),
    path('om/ecarts/<int:pk>/ticket-aspekt/', views.om_enregistrer_ticket_aspekt_vue, name='om_enregistrer_ticket_aspekt'),
    path('om/ecarts/<int:pk>/rollback-confirme/', views.om_confirmer_rollback_vue, name='om_confirmer_rollback'),
    path('om/ecarts/<int:pk>/resoudre-doublon/', views.om_resoudre_doublon_pamf_vue, name='om_resoudre_doublon_pamf'),
]
