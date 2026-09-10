from django import forms


class ImportMvolaForm(forms.Form):
    fichier = forms.FileField(
        label='Fichier CSV MVOLA',
        help_text='Format attendu : YYYY-MM-DD_reporting_PAMF.csv',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.csv'}),
    )

    def clean_fichier(self):
        fichier = self.cleaned_data['fichier']
        if not fichier.name.lower().endswith('.csv'):
            raise forms.ValidationError("Le fichier doit avoir l'extension .csv.")
        return fichier


class RapprochementForm(forms.Form):
    date = forms.DateField(
        label='Date a rapprocher',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
