from django.urls import path

from . import views

app_name = 'user'

urlpatterns = [
    path('inscription/', views.RegisterView.as_view(), name='register'),
    path('activation/<uidb64>/<token>/', views.activate, name='activate'),
    path('connexion/', views.InteropLoginView.as_view(), name='login'),
    path('deconnexion/', views.InteropLogoutView.as_view(), name='logout'),
    path('roles/', views.roles_liste, name='roles_liste'),
    path('roles/nouveau/', views.role_creer, name='role_creer'),
    path('roles/<int:pk>/modifier/', views.role_modifier, name='role_modifier'),
    path('roles/<int:pk>/supprimer/', views.role_supprimer, name='role_supprimer'),
    path('utilisateurs/', views.utilisateurs_liste, name='utilisateurs_liste'),
    path('utilisateurs/nouveau/', views.utilisateur_creer, name='utilisateur_creer'),
    path('utilisateurs/<int:pk>/roles/', views.utilisateur_roles, name='utilisateur_roles'),
    path('utilisateurs/<int:pk>/activer-desactiver/', views.utilisateur_toggle_actif, name='utilisateur_toggle_actif'),
    path(
        'utilisateurs/<int:pk>/mot-de-passe/',
        views.utilisateur_changer_mot_de_passe,
        name='utilisateur_changer_mot_de_passe',
    ),
]
