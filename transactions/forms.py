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


TYPE_OPERATION_CHOICES = [('', 'Tous'), ('WTB', 'WTB'), ('BTW', 'BTW')]


class FiltreMvolaForm(forms.Form):
    date_min = forms.DateField(required=False, label='Du',
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}))
    date_max = forms.DateField(required=False, label='Au',
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}))
    transid_mvola = forms.CharField(required=False, label='TRANSID',
                                     widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    msisdn = forms.CharField(required=False, label='MSISDN',
                              widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    nom = forms.CharField(required=False, label='Nom',
                           widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    type_operation = forms.ChoiceField(required=False, label='Type', choices=TYPE_OPERATION_CHOICES,
                                        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))


class FiltrePamfForm(forms.Form):
    date_min = forms.DateField(required=False, label='Du',
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}))
    date_max = forms.DateField(required=False, label='Au',
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}))
    transid_mvola = forms.CharField(required=False, label='TRANSID',
                                     widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    r_autotransaction_id = forms.CharField(required=False, label='rAutotransactionID',
                                            widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
