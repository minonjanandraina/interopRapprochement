from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from core.htmx import is_htmx_request
from core.pagination import paginate

from .csv_mvola import FichierMvolaInvalide, importer_fichier_mvola
from .forms import FiltreMvolaForm, FiltrePamfForm, ImportMvolaForm, RapprochementForm
from .models import ImportFichierMvola, Rapprochement, ResultatRapprochement, TransactionMvola, TransactionPamf
from .services_rapprochement import CsvMvolaNonImporte, lancer_rapprochement

PAGE_SIZE = 25


@login_required
def mvola_import(request):
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
                return redirect('transactions:mvola_import')
    else:
        form = ImportMvolaForm()

    historique = ImportFichierMvola.objects.all()[:20]
    return render(request, 'transactions/import_mvola.html', {
        'form': form, 'historique': historique, 'active_tab': 'import', 'active_service': 'mvola',
    })


@login_required
def mvola_rapprochement(request):
    if request.method == 'POST':
        form = RapprochementForm(request.POST)
        if form.is_valid():
            date_cible = form.cleaned_data['date']
            try:
                rapprochement = lancer_rapprochement(date_cible, request.user)
            except CsvMvolaNonImporte as exc:
                form.add_error('date', str(exc))
            else:
                if rapprochement.statut == Rapprochement.Statut.ECHEC:
                    messages.error(request, f"Echec du rapprochement : {rapprochement.message_erreur}")
                else:
                    messages.success(
                        request,
                        f"Rapprochement du {date_cible.strftime('%d/%m/%Y')} termine : "
                        f"{rapprochement.nb_success} rapprochee(s), "
                        f"{rapprochement.nb_orphelines_mvola} orpheline(s) MVOLA, "
                        f"{rapprochement.nb_orphelines_pamf} orpheline(s) PAMF."
                    )
                return redirect('transactions:mvola_rapprochement')
    else:
        form = RapprochementForm()

    historique = Rapprochement.objects.all()[:30]
    return render(request, 'transactions/rapprochement_mvola.html', {
        'form': form, 'historique': historique, 'active_tab': 'rapprochement', 'active_service': 'mvola',
    })


@login_required
def mvola_rapprochement_detail(request, pk):
    rapprochement = get_object_or_404(Rapprochement, pk=pk)
    return render(request, 'transactions/partials/rapprochement_modal.html', {'rapprochement': rapprochement})


@login_required
def mvola_rapprochement_lignes(request, pk, type_donnee):
    rapprochement = get_object_or_404(Rapprochement, pk=pk)

    if type_donnee == 'mvola':
        queryset = TransactionMvola.objects.filter(date_trans__date=rapprochement.date)
    elif type_donnee == 'pamf':
        queryset = TransactionPamf.objects.filter(posting_date=rapprochement.date)
    elif type_donnee == 'orphelines':
        queryset = rapprochement.resultats.exclude(
            statut=ResultatRapprochement.Statut.SUCCESS
        ).select_related('transaction_mvola', 'transaction_pamf')
    else:
        queryset = ResultatRapprochement.objects.none()

    page_obj = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'transactions/partials/rapprochement_lignes.html', {
        'rapprochement': rapprochement, 'type_donnee': type_donnee, 'page_obj': page_obj,
    })


@login_required
def mvola_liste_transactions(request):
    form = FiltreMvolaForm(request.GET or None)
    queryset = TransactionMvola.objects.all()
    if form.is_valid():
        data = form.cleaned_data
        if data['date_min']:
            queryset = queryset.filter(date_trans__date__gte=data['date_min'])
        if data['date_max']:
            queryset = queryset.filter(date_trans__date__lte=data['date_max'])
        if data['transid_mvola']:
            queryset = queryset.filter(transid_mvola__icontains=data['transid_mvola'])
        if data['msisdn']:
            queryset = queryset.filter(msisdn__icontains=data['msisdn'])
        if data['nom']:
            queryset = queryset.filter(nom__icontains=data['nom'])
        if data['type_operation']:
            queryset = queryset.filter(type_operation=data['type_operation'])

    page_obj, querystring = paginate(request, queryset)
    context = {'form': form, 'page_obj': page_obj, 'querystring': querystring}

    if is_htmx_request(request):
        return render(request, 'transactions/partials/liste_mvola_table.html', context)

    context.update({'active_tab': 'liste_mvola', 'active_service': 'mvola'})
    return render(request, 'transactions/liste_mvola.html', context)


@login_required
def mvola_liste_pamf(request):
    form = FiltrePamfForm(request.GET or None)
    queryset = TransactionPamf.objects.all()
    if form.is_valid():
        data = form.cleaned_data
        if data['date_min']:
            queryset = queryset.filter(posting_date__gte=data['date_min'])
        if data['date_max']:
            queryset = queryset.filter(posting_date__lte=data['date_max'])
        if data['transid_mvola']:
            queryset = queryset.filter(transid_mvola__icontains=data['transid_mvola'])
        if data['r_autotransaction_id']:
            queryset = queryset.filter(r_autotransaction_id__icontains=data['r_autotransaction_id'])
        if data['is_success']:
            queryset = queryset.filter(is_success=(data['is_success'] == '1'))

    page_obj, querystring = paginate(request, queryset)
    context = {'form': form, 'page_obj': page_obj, 'querystring': querystring}

    if is_htmx_request(request):
        return render(request, 'transactions/partials/liste_pamf_table.html', context)

    context.update({'active_tab': 'liste_pamf', 'active_service': 'mvola'})
    return render(request, 'transactions/liste_pamf.html', context)
