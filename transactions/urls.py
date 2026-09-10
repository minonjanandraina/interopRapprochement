from django.urls import path

from . import views

app_name = 'transactions'

urlpatterns = [
    path('mvola/import/', views.import_mvola, name='import_mvola'),
    path('pamf/import/', views.import_pamf, name='import_pamf'),
]
