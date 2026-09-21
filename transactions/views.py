from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core import reports
from core.htmx import is_htmx_request
from core.pagination import paginate
from user import privileges
from user.decorators import privilege_required

from .csv_mvola import FichierMvolaInvalide, importer_fichier_mvola
from .forms import (
    FiltreMvolaForm,
    FiltreOMForm,
    FiltrePamfForm,
    FiltrePamfOMForm,
    ImportMvolaForm,
    ImportOMForm,
    RapprochementForm,
)
from .models import (
    ImportFichierMvola,
    ImportFichierOM,
    Rapprochement,
    RapprochementOM,
    ResultatRapprochement,
    ResultatRapprochementOM,
    TransactionMvola,
    TransactionOM,
    TransactionPamf,
    TransactionPamfOM,
)
from .services_rapprochement import CsvMvolaNonImporte, JourneeCbsNonTerminee, lancer_rapprochement
from .services_rapprochement_om import FichierOMNonImporte, lancer_rapprochement_om
from .xls_om import FichierOMInvalide, importer_fichier_om

PAGE_SIZE = 25

COLONNES_MVOLA = [
    ('TRANSID', lambda t: t.transid_mvola),
    ('Date', lambda t: t.date_trans),
    ('MSISDN', lambda t: t.msisdn),
    ('Nom', lambda t: t.nom),
    ('Montant', lambda t: t.amount),
    ('Type', lambda t: t.type_operation),
    ('Etat', lambda t: t.state),
]

COLONNES_PAMF = [
    ('TRANSID', lambda t: t.transid_mvola),
    ('Date', lambda t: t.posting_date),
    ('rAutotransactionID', lambda t: t.r_autotransaction_id),
    ('Heure', lambda t: t.time),
    ('Statut CBS', lambda t: 'Succes' if t.is_success else 'Echec'),
    ('Note', lambda t: t.note),
]

COLONNES_ORPHELINES = [
    ('TRANSID', lambda r: r.transid_mvola),
    ('Statut', lambda r: r.get_statut_display()),
    ('Action recommandee', lambda r: r.action_recommandee.label if r.action_recommandee else None),
    ('MSISDN / Nom (MVOLA)', lambda r: f'{r.transaction_mvola.msisdn} - {r.transaction_mvola.nom}' if r.transaction_mvola else None),
    ('Montant (MVOLA)', lambda r: r.transaction_mvola.amount if r.transaction_mvola else None),
    ('rAutotransactionID (PAMF)', lambda r: r.transaction_pamf.r_autotransaction_id if r.transaction_pamf else None),
]

TYPE_DONNEE_LABELS = {
    'mvola': 'Transactions MVOLA',
    'pamf': 'Transactions PAMF',
    'orphelines': 'Orphelines',
}

COLONNES_OM = [
    ('TRANSID', lambda t: t.transid_om),
    ('Date', lambda t: t.date_trans),
    ('MSISDN', lambda t: t.msisdn),
    ('Montant', lambda t: t.montant),
    ('Service', lambda t: t.service),
    ('Statut', lambda t: t.statut),
]

COLONNES_PAMF_OM = [
    ('TRANSID', lambda t: t.transid_om),
    ('Date', lambda t: t.posting_date),
    ('rAutotransactionID', lambda t: t.r_autotransaction_id),
    ('Heure', lambda t: t.time),
    ('Montant', lambda t: t.montant),
    ('Statut CBS', lambda t: 'Succes' if t.is_success else 'Echec'),
    ('Note', lambda t: t.note),
]

COLONNES_ORPHELINES_OM = [
    ('TRANSID', lambda r: r.transid_om),
    ('Statut', lambda r: r.get_statut_display()),
    ('Action recommandee', lambda r: r.action_recommandee.label if r.action_recommandee else None),
    ('MSISDN (OM)', lambda r: r.transaction_om.msisdn if r.transaction_om else None),
    ('Montant (OM)', lambda r: r.transaction_om.montant if r.transaction_om else None),
    ('rAutotransactionID (PAMF)', lambda r: r.transaction_pamf.r_autotransaction_id if r.transaction_pamf else None),
]

TYPE_DONNEE_LABELS_OM = {
    'om': 'Transactions Orange Money',
    'pamf': 'Transactions PAMF',
    'orphelines': 'Orphelines',
}


def _filtrer_mvola(request):
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
    return queryset, form


def _filtrer_pamf(request):
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
    return queryset, form


def _rapprochement_lignes_queryset(rapprochement, type_donnee):
    if type_donnee == 'mvola':
        return TransactionMvola.objects.filter(date_trans__date=rapprochement.date), COLONNES_MVOLA
    if type_donnee == 'pamf':
        return TransactionPamf.objects.filter(posting_date=rapprochement.date), COLONNES_PAMF
    if type_donnee == 'orphelines':
        queryset = rapprochement.resultats.exclude(
            statut=ResultatRapprochement.Statut.SUCCESS
        ).select_related('transaction_mvola', 'transaction_pamf')
        return queryset, COLONNES_ORPHELINES
    return ResultatRapprochement.objects.none(), COLONNES_ORPHELINES


def _meta_rapprochement_lignes(request, rapprochement, type_donnee, nb_lignes, avec_export_urls):
    filtres = [
        ('Date du rapprochement', rapprochement.date.strftime('%d/%m/%Y')),
        ('Type de donnees', TYPE_DONNEE_LABELS.get(type_donnee, type_donnee)),
    ]
    export_excel_url = export_pdf_url = None
    if avec_export_urls:
        export_excel_url, export_pdf_url = reports.urls_export(
            request, 'transactions:mvola_rapprochement_lignes_export', rapprochement.pk, type_donnee,
        )
    return reports.build_meta(
        request,
        titre=f"Rapprochement {rapprochement.date.strftime('%d/%m/%Y')} - {TYPE_DONNEE_LABELS.get(type_donnee, type_donnee)}",
        module_source='Moteur de rapprochement MVOLA / PAMF',
        filtres=filtres,
        nb_lignes=nb_lignes,
        export_excel_url=export_excel_url,
        export_pdf_url=export_pdf_url,
    )


@privilege_required(privileges.IMPORTER_CSV_MVOLA)
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


def _dates_de_la_plage(date_from, date_to):
    nb_jours = (date_to - date_from).days + 1
    return [date_from + timedelta(days=i) for i in range(nb_jours)]


def _lancer_rapprochement_date(date_cible, user):
    """Lance le rapprochement pour une date et retourne (ok, message), sans jamais lever
    d'exception : utilise a la fois par le fallback sans JS et par l'endpoint AJAX par date."""
    try:
        rapprochement = lancer_rapprochement(date_cible, user)
    except (CsvMvolaNonImporte, JourneeCbsNonTerminee) as exc:
        return False, str(exc)

    if rapprochement.statut == Rapprochement.Statut.ECHEC:
        return False, f"Echec du rapprochement : {rapprochement.message_erreur}"

    return True, (
        f"Rapprochement du {date_cible.strftime('%d/%m/%Y')} termine : "
        f"{rapprochement.nb_success} rapprochee(s), "
        f"{rapprochement.nb_orphelines_mvola} orpheline(s) MVOLA, "
        f"{rapprochement.nb_orphelines_pamf} orpheline(s) PAMF."
    )


@privilege_required([privileges.LANCER_RAPPROCHEMENT, privileges.CONSULTER_RAPPROCHEMENT])
def mvola_rapprochement(request):
    if request.method == 'POST':
        if not request.user.has_privilege(privileges.LANCER_RAPPROCHEMENT):
            raise PermissionDenied("Vous n'avez pas le privilege necessaire pour lancer un rapprochement.")
        form = RapprochementForm(request.POST)
        if form.is_valid():
            # Fallback sans JS : la plage est traitee sequentiellement dans la requete (pas de
            # suivi "en cours"/"a suivre" en direct, cf. modal cote JS pour le cas normal).
            for date_cible in _dates_de_la_plage(form.cleaned_data['date_from'], form.cleaned_data['date_to']):
                ok, message = _lancer_rapprochement_date(date_cible, request.user)
                (messages.success if ok else messages.error)(request, message)
            return redirect('transactions:mvola_rapprochement')
    else:
        form = RapprochementForm()

    historique = Rapprochement.objects.all()[:30]
    can_launch_reconciliation = request.user.has_privilege(privileges.LANCER_RAPPROCHEMENT)
    return render(request, 'transactions/rapprochement_mvola.html', {
        'form': form, 'historique': historique, 'active_tab': 'rapprochement', 'active_service': 'mvola',
        'can_launch_reconciliation': can_launch_reconciliation,
    })


@require_POST
@privilege_required(privileges.LANCER_RAPPROCHEMENT)
def mvola_rapprochement_lancer_date(request):
    """Lance le rapprochement pour une seule date, appele en AJAX par le modal de lancement sur
    une plage (cf. rapprochement_mvola.html) : le navigateur orchestre la sequence date par date
    pour afficher une progression en direct, sans introduire de file d'attente serveur (le
    moteur reste synchrone, cf. CLAUDE.md Sprint 5)."""
    date_str = request.POST.get('date', '')
    try:
        date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'date': date_str, 'ok': False, 'message': 'Date invalide.'}, status=400)

    ok, message = _lancer_rapprochement_date(date_cible, request.user)
    return JsonResponse({'date': date_str, 'ok': ok, 'message': message})


@login_required
def mvola_rapprochement_detail(request, pk):
    rapprochement = get_object_or_404(Rapprochement, pk=pk)
    return render(request, 'transactions/partials/rapprochement_modal.html', {'rapprochement': rapprochement})


@login_required
def mvola_rapprochement_lignes(request, pk, type_donnee):
    rapprochement = get_object_or_404(Rapprochement, pk=pk)
    queryset, _colonnes = _rapprochement_lignes_queryset(rapprochement, type_donnee)

    page_obj = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get('page'))
    meta = _meta_rapprochement_lignes(request, rapprochement, type_donnee, queryset.count(), avec_export_urls=True)
    return render(request, 'transactions/partials/rapprochement_lignes.html', {
        'rapprochement': rapprochement, 'type_donnee': type_donnee, 'page_obj': page_obj, 'meta': meta,
    })


@login_required
def mvola_rapprochement_lignes_export(request, pk, type_donnee, format):
    rapprochement = get_object_or_404(Rapprochement, pk=pk)
    queryset, colonnes = _rapprochement_lignes_queryset(rapprochement, type_donnee)
    meta = _meta_rapprochement_lignes(request, rapprochement, type_donnee, queryset.count(), avec_export_urls=False)
    nom_fichier = f'rapprochement_{rapprochement.date.isoformat()}_{type_donnee}'
    return reports.exporter(format, meta, colonnes, queryset, nom_fichier)


@login_required
def mvola_liste_transactions(request):
    queryset, form = _filtrer_mvola(request)
    page_obj, querystring = paginate(request, queryset)
    export_excel_url, export_pdf_url = reports.urls_export(request, 'transactions:mvola_liste_transactions_export')
    meta = reports.build_meta(
        request,
        titre='Transactions MVOLA',
        module_source='Import CSV MVOLA (source 1)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=page_obj.paginator.count,
        export_excel_url=export_excel_url,
        export_pdf_url=export_pdf_url,
    )
    context = {'form': form, 'page_obj': page_obj, 'querystring': querystring, 'meta': meta}

    if is_htmx_request(request):
        return render(request, 'transactions/partials/liste_mvola_table.html', context)

    context.update({'active_tab': 'liste_mvola', 'active_service': 'mvola'})
    return render(request, 'transactions/liste_mvola.html', context)


@login_required
def mvola_liste_transactions_export(request, format):
    queryset, form = _filtrer_mvola(request)
    meta = reports.build_meta(
        request,
        titre='Transactions MVOLA',
        module_source='Import CSV MVOLA (source 1)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=queryset.count(),
    )
    return reports.exporter(format, meta, COLONNES_MVOLA, queryset, 'transactions_mvola')


@login_required
def mvola_liste_pamf(request):
    queryset, form = _filtrer_pamf(request)
    page_obj, querystring = paginate(request, queryset)
    export_excel_url, export_pdf_url = reports.urls_export(request, 'transactions:mvola_liste_pamf_export')
    meta = reports.build_meta(
        request,
        titre='Transactions PAMF',
        module_source='Requete base CBS (source 2)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=page_obj.paginator.count,
        export_excel_url=export_excel_url,
        export_pdf_url=export_pdf_url,
    )
    context = {'form': form, 'page_obj': page_obj, 'querystring': querystring, 'meta': meta}

    if is_htmx_request(request):
        return render(request, 'transactions/partials/liste_pamf_table.html', context)

    context.update({'active_tab': 'liste_pamf', 'active_service': 'mvola'})
    return render(request, 'transactions/liste_pamf.html', context)


@login_required
def mvola_liste_pamf_export(request, format):
    queryset, form = _filtrer_pamf(request)
    meta = reports.build_meta(
        request,
        titre='Transactions PAMF',
        module_source='Requete base CBS (source 2)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=queryset.count(),
    )
    return reports.exporter(format, meta, COLONNES_PAMF, queryset, 'transactions_pamf')


# --- Orange Money (OM) -------------------------------------------------------------------------
# Miroir des vues MVOLA ci-dessus - cf. CLAUDE.md, Decisions prises (duplication OM).


def _filtrer_om(request):
    form = FiltreOMForm(request.GET or None)
    queryset = TransactionOM.objects.all()
    if form.is_valid():
        data = form.cleaned_data
        if data['date_min']:
            queryset = queryset.filter(date_trans__date__gte=data['date_min'])
        if data['date_max']:
            queryset = queryset.filter(date_trans__date__lte=data['date_max'])
        if data['transid_om']:
            queryset = queryset.filter(transid_om__icontains=data['transid_om'])
        if data['msisdn']:
            queryset = queryset.filter(msisdn__icontains=data['msisdn'])
    return queryset, form


def _filtrer_pamf_om(request):
    form = FiltrePamfOMForm(request.GET or None)
    queryset = TransactionPamfOM.objects.all()
    if form.is_valid():
        data = form.cleaned_data
        if data['date_min']:
            queryset = queryset.filter(posting_date__gte=data['date_min'])
        if data['date_max']:
            queryset = queryset.filter(posting_date__lte=data['date_max'])
        if data['transid_om']:
            queryset = queryset.filter(transid_om__icontains=data['transid_om'])
        if data['r_autotransaction_id']:
            queryset = queryset.filter(r_autotransaction_id__icontains=data['r_autotransaction_id'])
        if data['is_success']:
            queryset = queryset.filter(is_success=(data['is_success'] == '1'))
    return queryset, form


def _rapprochement_lignes_queryset_om(rapprochement, type_donnee):
    if type_donnee == 'om':
        return TransactionOM.objects.filter(date_trans__date=rapprochement.date), COLONNES_OM
    if type_donnee == 'pamf':
        return TransactionPamfOM.objects.filter(posting_date=rapprochement.date), COLONNES_PAMF_OM
    if type_donnee == 'orphelines':
        queryset = rapprochement.resultats.exclude(
            statut=ResultatRapprochementOM.Statut.SUCCESS
        ).select_related('transaction_om', 'transaction_pamf')
        return queryset, COLONNES_ORPHELINES_OM
    return ResultatRapprochementOM.objects.none(), COLONNES_ORPHELINES_OM


def _meta_rapprochement_lignes_om(request, rapprochement, type_donnee, nb_lignes, avec_export_urls):
    filtres = [
        ('Date du rapprochement', rapprochement.date.strftime('%d/%m/%Y')),
        ('Type de donnees', TYPE_DONNEE_LABELS_OM.get(type_donnee, type_donnee)),
    ]
    export_excel_url = export_pdf_url = None
    if avec_export_urls:
        export_excel_url, export_pdf_url = reports.urls_export(
            request, 'transactions:om_rapprochement_lignes_export', rapprochement.pk, type_donnee,
        )
    return reports.build_meta(
        request,
        titre=f"Rapprochement {rapprochement.date.strftime('%d/%m/%Y')} - {TYPE_DONNEE_LABELS_OM.get(type_donnee, type_donnee)}",
        module_source='Moteur de rapprochement Orange Money / PAMF',
        filtres=filtres,
        nb_lignes=nb_lignes,
        export_excel_url=export_excel_url,
        export_pdf_url=export_pdf_url,
    )


@privilege_required(privileges.IMPORTER_FICHIER_OM)
def om_import(request):
    if request.method == 'POST':
        form = ImportOMForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                import_obj = importer_fichier_om(form.cleaned_data['fichier'], request.user)
            except FichierOMInvalide as exc:
                form.add_error('fichier', str(exc))
            else:
                messages.success(
                    request,
                    f"Import termine : {import_obj.nb_lignes_inserees} transaction(s) inseree(s), "
                    f"{import_obj.nb_doublons} doublon(s) ignore(s), "
                    f"{import_obj.nb_hors_succes} ligne(s) hors statut Succes ignoree(s), "
                    f"{import_obj.nb_erreurs} erreur(s) de ligne."
                )
                return redirect('transactions:om_import')
    else:
        form = ImportOMForm()

    historique = ImportFichierOM.objects.all()[:20]
    return render(request, 'transactions/import_om.html', {
        'form': form, 'historique': historique, 'active_tab': 'import', 'active_service': 'om',
    })


def _lancer_rapprochement_date_om(date_cible, user):
    """Lance le rapprochement OM pour une date et retourne (ok, message), sans jamais lever
    d'exception. Cf. _lancer_rapprochement_date (MVOLA)."""
    try:
        rapprochement = lancer_rapprochement_om(date_cible, user)
    except (FichierOMNonImporte, JourneeCbsNonTerminee) as exc:
        return False, str(exc)

    if rapprochement.statut == RapprochementOM.Statut.ECHEC:
        return False, f"Echec du rapprochement : {rapprochement.message_erreur}"

    return True, (
        f"Rapprochement du {date_cible.strftime('%d/%m/%Y')} termine : "
        f"{rapprochement.nb_success} rapprochee(s), "
        f"{rapprochement.nb_orphelines_om} orpheline(s) Orange Money, "
        f"{rapprochement.nb_orphelines_pamf} orpheline(s) PAMF."
    )


@privilege_required([privileges.LANCER_RAPPROCHEMENT, privileges.CONSULTER_RAPPROCHEMENT])
def om_rapprochement(request):
    if request.method == 'POST':
        if not request.user.has_privilege(privileges.LANCER_RAPPROCHEMENT):
            raise PermissionDenied("Vous n'avez pas le privilege necessaire pour lancer un rapprochement.")
        form = RapprochementForm(request.POST)
        if form.is_valid():
            for date_cible in _dates_de_la_plage(form.cleaned_data['date_from'], form.cleaned_data['date_to']):
                ok, message = _lancer_rapprochement_date_om(date_cible, request.user)
                (messages.success if ok else messages.error)(request, message)
            return redirect('transactions:om_rapprochement')
    else:
        form = RapprochementForm()

    historique = RapprochementOM.objects.all()[:30]
    can_launch_reconciliation = request.user.has_privilege(privileges.LANCER_RAPPROCHEMENT)
    return render(request, 'transactions/rapprochement_om.html', {
        'form': form, 'historique': historique, 'active_tab': 'rapprochement', 'active_service': 'om',
        'can_launch_reconciliation': can_launch_reconciliation,
    })


@require_POST
@privilege_required(privileges.LANCER_RAPPROCHEMENT)
def om_rapprochement_lancer_date(request):
    """Cf. mvola_rapprochement_lancer_date : appele en AJAX par le modal de lancement sur une
    plage, orchestre la sequence date par date cote navigateur."""
    date_str = request.POST.get('date', '')
    try:
        date_cible = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'date': date_str, 'ok': False, 'message': 'Date invalide.'}, status=400)

    ok, message = _lancer_rapprochement_date_om(date_cible, request.user)
    return JsonResponse({'date': date_str, 'ok': ok, 'message': message})


@login_required
def om_rapprochement_detail(request, pk):
    rapprochement = get_object_or_404(RapprochementOM, pk=pk)
    return render(request, 'transactions/partials/rapprochement_om_modal.html', {'rapprochement': rapprochement})


@login_required
def om_rapprochement_lignes(request, pk, type_donnee):
    rapprochement = get_object_or_404(RapprochementOM, pk=pk)
    queryset, _colonnes = _rapprochement_lignes_queryset_om(rapprochement, type_donnee)

    page_obj = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get('page'))
    meta = _meta_rapprochement_lignes_om(request, rapprochement, type_donnee, queryset.count(), avec_export_urls=True)
    return render(request, 'transactions/partials/rapprochement_om_lignes.html', {
        'rapprochement': rapprochement, 'type_donnee': type_donnee, 'page_obj': page_obj, 'meta': meta,
    })


@login_required
def om_rapprochement_lignes_export(request, pk, type_donnee, format):
    rapprochement = get_object_or_404(RapprochementOM, pk=pk)
    queryset, colonnes = _rapprochement_lignes_queryset_om(rapprochement, type_donnee)
    meta = _meta_rapprochement_lignes_om(request, rapprochement, type_donnee, queryset.count(), avec_export_urls=False)
    nom_fichier = f'rapprochement_om_{rapprochement.date.isoformat()}_{type_donnee}'
    return reports.exporter(format, meta, colonnes, queryset, nom_fichier)


@login_required
def om_liste_transactions(request):
    queryset, form = _filtrer_om(request)
    page_obj, querystring = paginate(request, queryset)
    export_excel_url, export_pdf_url = reports.urls_export(request, 'transactions:om_liste_transactions_export')
    meta = reports.build_meta(
        request,
        titre='Transactions Orange Money',
        module_source='Import XLS Orange Money (source 1)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=page_obj.paginator.count,
        export_excel_url=export_excel_url,
        export_pdf_url=export_pdf_url,
    )
    context = {'form': form, 'page_obj': page_obj, 'querystring': querystring, 'meta': meta}

    if is_htmx_request(request):
        return render(request, 'transactions/partials/liste_om_table.html', context)

    context.update({'active_tab': 'liste_om', 'active_service': 'om'})
    return render(request, 'transactions/liste_om.html', context)


@login_required
def om_liste_transactions_export(request, format):
    queryset, form = _filtrer_om(request)
    meta = reports.build_meta(
        request,
        titre='Transactions Orange Money',
        module_source='Import XLS Orange Money (source 1)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=queryset.count(),
    )
    return reports.exporter(format, meta, COLONNES_OM, queryset, 'transactions_om')


@login_required
def om_liste_pamf(request):
    queryset, form = _filtrer_pamf_om(request)
    page_obj, querystring = paginate(request, queryset)
    export_excel_url, export_pdf_url = reports.urls_export(request, 'transactions:om_liste_pamf_export')
    meta = reports.build_meta(
        request,
        titre='Transactions PAMF (Orange Money)',
        module_source='Requete base CBS (source 2, rMerchantID=9)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=page_obj.paginator.count,
        export_excel_url=export_excel_url,
        export_pdf_url=export_pdf_url,
    )
    context = {'form': form, 'page_obj': page_obj, 'querystring': querystring, 'meta': meta}

    if is_htmx_request(request):
        return render(request, 'transactions/partials/liste_pamf_om_table.html', context)

    context.update({'active_tab': 'liste_pamf', 'active_service': 'om'})
    return render(request, 'transactions/liste_pamf_om.html', context)


@login_required
def om_liste_pamf_export(request, format):
    queryset, form = _filtrer_pamf_om(request)
    meta = reports.build_meta(
        request,
        titre='Transactions PAMF (Orange Money)',
        module_source='Requete base CBS (source 2, rMerchantID=9)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=queryset.count(),
    )
    return reports.exporter(format, meta, COLONNES_PAMF_OM, queryset, 'transactions_pamf_om')
