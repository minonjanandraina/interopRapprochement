from django.urls import path

from . import views

app_name = 'ecarts'

urlpatterns = [
    path('mvola/ecarts/', views.mvola_liste, name='mvola_liste'),
    path('mvola/ecarts/<int:pk>/', views.detail, name='detail'),
    path('mvola/ecarts/<int:pk>/commentaire/', views.ajouter_commentaire_vue, name='ajouter_commentaire'),
    path('mvola/ecarts/<int:pk>/statut/', views.changer_statut_vue, name='changer_statut'),
    path('mvola/ecarts/<int:pk>/piece-jointe/', views.ajouter_piece_jointe_vue, name='ajouter_piece_jointe'),
    path('mvola/ecarts/<int:pk>/ticket-aspekt/', views.enregistrer_ticket_aspekt_vue, name='enregistrer_ticket_aspekt'),
    path('mvola/ecarts/<int:pk>/rollback-confirme/', views.confirmer_rollback_vue, name='confirmer_rollback'),
]
