from django.urls import path

from . import views

app_name = 'user'

urlpatterns = [
    path('inscription/', views.RegisterView.as_view(), name='register'),
    path('activation/<uidb64>/<token>/', views.activate, name='activate'),
    path('connexion/', views.InteropLoginView.as_view(), name='login'),
    path('deconnexion/', views.InteropLogoutView.as_view(), name='logout'),
]
