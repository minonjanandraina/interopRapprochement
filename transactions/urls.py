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
]
