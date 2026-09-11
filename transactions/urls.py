from django.urls import path

from . import views

app_name = 'transactions'

urlpatterns = [
    path('mvola/import/', views.mvola_import, name='mvola_import'),
    path('mvola/rapprochement/', views.mvola_rapprochement, name='mvola_rapprochement'),
    path('mvola/rapprochement/<int:pk>/detail/', views.mvola_rapprochement_detail, name='mvola_rapprochement_detail'),
    path(
        'mvola/rapprochement/<int:pk>/lignes/<str:type_donnee>/',
        views.mvola_rapprochement_lignes,
        name='mvola_rapprochement_lignes',
    ),
    path(
        'mvola/rapprochement/<int:pk>/lignes/<str:type_donnee>/export/<str:format>/',
        views.mvola_rapprochement_lignes_export,
        name='mvola_rapprochement_lignes_export',
    ),
    path('mvola/transactions/', views.mvola_liste_transactions, name='mvola_liste_transactions'),
    path('mvola/transactions/export/<str:format>/', views.mvola_liste_transactions_export, name='mvola_liste_transactions_export'),
    path('mvola/pamf/', views.mvola_liste_pamf, name='mvola_liste_pamf'),
    path('mvola/pamf/export/<str:format>/', views.mvola_liste_pamf_export, name='mvola_liste_pamf_export'),
]
