from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .csv_mvola import FichierMvolaInvalide, importer_fichier_mvola
from .forms import ImportMvolaForm, ImportPamfForm
from .models import ImportFichierMvola, ImportRequetePamf
from .services_pamf import importer_transactions_pamf


@login_required
def import_mvola(request):
    if request.method == 'POST':
        form = ImportMvolaForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                import_obj = importer_fichier_mvola(form.cleaned_data['fichier'], request.user)
            except FichierMvolaInvalide as exc:
                form.add_error('fichier', str(exc))
            else:
                messages.success(
                    request,
                    f"Import termine : {import_obj.nb_lignes_inserees} transaction(s) inseree(s), "
                    f"{import_obj.nb_doublons} doublon(s) ignore(s), {import_obj.nb_erreurs} erreur(s) de ligne."
                )
                return redirect('transactions:import_mvola')
    else:
        form = ImportMvolaForm()

    historique = ImportFichierMvola.objects.all()[:20]
    return render(request, 'transactions/import_mvola.html', {'form': form, 'historique': historique})


@login_required
def import_pamf(request):
    if request.method == 'POST':
        form = ImportPamfForm(request.POST)
        if form.is_valid():
            import_obj = importer_transactions_pamf(form.cleaned_data['date_requete'], request.user)
            if import_obj.statut == ImportRequetePamf.Statut.SUCCES:
                messages.success(
                    request,
                    f"Import termine : {import_obj.nb_lignes} transaction(s) recuperee(s) du CBS, "
                    f"{import_obj.nb_doublons} doublon(s) ignore(s)."
                )
            else:
                messages.error(request, f"Echec de la requete CBS : {import_obj.message_erreur}")
            return redirect('transactions:import_pamf')
    else:
        form = ImportPamfForm()

    historique = ImportRequetePamf.objects.all()[:20]
    return render(request, 'transactions/import_pamf.html', {'form': form, 'historique': historique})
