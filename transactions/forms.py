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


RAPPROCHEMENT_PLAGE_MAX_JOURS = 31


class RapprochementForm(forms.Form):
    date_from = forms.DateField(
        label='Du',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    date_to = forms.DateField(
        label='Au',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get('date_from')
        date_to = cleaned.get('date_to')
        if date_from and date_to:
            if date_from > date_to:
                raise forms.ValidationError("La date de debut doit etre anterieure ou egale a la date de fin.")
            nb_jours = (date_to - date_from).days + 1
            if nb_jours > RAPPROCHEMENT_PLAGE_MAX_JOURS:
                raise forms.ValidationError(
                    f"La plage ne peut pas depasser {RAPPROCHEMENT_PLAGE_MAX_JOURS} jours "
                    f"(le moteur de rapprochement reste synchrone, cf. CLAUDE.md)."
                )
        return cleaned


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
    is_success = forms.ChoiceField(required=False, label='Statut CBS',
                                    choices=[('', 'Tous'), ('1', 'Succes'), ('0', 'Echec')],
                                    widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))


class ImportOMForm(forms.Form):
    fichier = forms.FileField(
        label='Fichier Orange Money',
        help_text='Format attendu : Daily-ChannelUserTransactionReport-<compte>-YYYYMMDD.xls',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xls'}),
    )

    def clean_fichier(self):
        fichier = self.cleaned_data['fichier']
        if not fichier.name.lower().endswith('.xls'):
            raise forms.ValidationError("Le fichier doit avoir l'extension .xls.")
        return fichier


class FiltreOMForm(forms.Form):
    date_min = forms.DateField(required=False, label='Du',
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}))
    date_max = forms.DateField(required=False, label='Au',
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}))
    transid_om = forms.CharField(required=False, label='Reference OM',
                                  widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    msisdn = forms.CharField(required=False, label='MSISDN',
                              widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))


class FiltrePamfOMForm(forms.Form):
    date_min = forms.DateField(required=False, label='Du',
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}))
    date_max = forms.DateField(required=False, label='Au',
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}))
    transid_om = forms.CharField(required=False, label='Reference OM',
                                  widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    r_autotransaction_id = forms.CharField(required=False, label='rAutotransactionID',
                                            widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}))
    is_success = forms.ChoiceField(required=False, label='Statut CBS',
                                    choices=[('', 'Tous'), ('1', 'Succes'), ('0', 'Echec')],
                                    widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
