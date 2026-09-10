from django.urls import path

from . import views

app_name = 'ecarts'

urlpatterns = [
    path('mvola/ecarts/', views.mvola_liste, name='mvola_liste'),
]
