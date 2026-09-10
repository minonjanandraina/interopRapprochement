from django import forms

from .models import Ecart


class FiltreEcartForm(forms.Form):
    date_min = forms.DateField(required=False, label='Du',
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}))
    date_max = forms.DateField(required=False, label='Au',
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}))
    transid_mvola = forms.CharField(required=False, label='TRANSID',
                                     widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    type_ecart = forms.ChoiceField(required=False, label='Type', choices=[('', 'Tous')] + Ecart.TypeEcart.choices,
                                    widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    statut = forms.ChoiceField(required=False, label='Statut', choices=[('', 'Tous')] + Ecart.Statut.choices,
                                widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))


class CommentaireForm(forms.Form):
    texte = forms.CharField(
        label='Commentaire',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class ChangerStatutForm(forms.Form):
    nouveau_statut = forms.ChoiceField(
        label='Nouveau statut', choices=Ecart.Statut.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class PieceJointeForm(forms.Form):
    fichier = forms.FileField(
        label='Piece jointe',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
    )
    commentaire = forms.CharField(
        required=False, label='Commentaire (optionnel)',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
