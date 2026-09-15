from django.urls import path

from . import views

app_name = 'transactions'

urlpatterns = [
    path('mvola/import/', views.mvola_import, name='mvola_import'),
    path('mvola/rapprochement/', views.mvola_rapprochement, name='mvola_rapprochement'),
    path(
        'mvola/rapprochement/lancer-date/',
        views.mvola_rapprochement_lancer_date,
        name='mvola_rapprochement_lancer_date',
    ),
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

    path('om/import/', views.om_import, name='om_import'),
    path('om/rapprochement/', views.om_rapprochement, name='om_rapprochement'),
    path(
        'om/rapprochement/lancer-date/',
        views.om_rapprochement_lancer_date,
        name='om_rapprochement_lancer_date',
    ),
    path('om/rapprochement/<int:pk>/detail/', views.om_rapprochement_detail, name='om_rapprochement_detail'),
    path(
        'om/rapprochement/<int:pk>/lignes/<str:type_donnee>/',
        views.om_rapprochement_lignes,
        name='om_rapprochement_lignes',
    ),
    path(
        'om/rapprochement/<int:pk>/lignes/<str:type_donnee>/export/<str:format>/',
        views.om_rapprochement_lignes_export,
        name='om_rapprochement_lignes_export',
    ),
    path('om/transactions/', views.om_liste_transactions, name='om_liste_transactions'),
    path('om/transactions/export/<str:format>/', views.om_liste_transactions_export, name='om_liste_transactions_export'),
    path('om/pamf/', views.om_liste_pamf, name='om_liste_pamf'),
    path('om/pamf/export/<str:format>/', views.om_liste_pamf_export, name='om_liste_pamf_export'),
]
