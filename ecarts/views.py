from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core import reports
from core.htmx import is_htmx_request
from core.pagination import paginate
from user import privileges
from user.decorators import privilege_required

from .forms import (
    ChangerStatutForm,
    CommentaireForm,
    FiltreEcartForm,
    PieceJointeForm,
    RollbackConfirmeForm,
    TicketAspektForm,
)
from .models import Ecart
from .services import (
    ajouter_commentaire,
    ajouter_piece_jointe,
    changer_statut,
    confirmer_rollback,
    enregistrer_ticket_aspekt,
)

COLONNES_ECARTS = [
    ('TRANSID', lambda e: e.transid_mvola),
    ('Date', lambda e: e.date_transaction),
    ('Type', lambda e: e.get_type_ecart_display()),
    ('Montant', lambda e: e.montant),
    ('Action recommandee', lambda e: e.action_recommandee.label if e.action_recommandee else None),
    ('Statut', lambda e: e.get_statut_display()),
    ('Detecte le', lambda e: e.detecte_le),
]


def _filtrer_ecarts(request):
    form = FiltreEcartForm(request.GET or None)
    queryset = Ecart.objects.select_related('resultat__transaction_mvola', 'resultat__transaction_pamf')
    if form.is_valid():
        data = form.cleaned_data
        if data['date_min']:
            queryset = queryset.filter(date_transaction__gte=data['date_min'])
        if data['date_max']:
            queryset = queryset.filter(date_transaction__lte=data['date_max'])
        if data['transid_mvola']:
            queryset = queryset.filter(transid_mvola__icontains=data['transid_mvola'])
        if data['type_ecart']:
            queryset = queryset.filter(type_ecart=data['type_ecart'])
        if data['statut']:
            queryset = queryset.filter(statut=data['statut'])
    return queryset, form


@login_required
def mvola_liste(request):
    queryset, form = _filtrer_ecarts(request)
    page_obj, querystring = paginate(request, queryset)
    export_excel_url, export_pdf_url = reports.urls_export(request, 'ecarts:mvola_liste_export')
    meta = reports.build_meta(
        request,
        titre='Ecarts MVOLA / PAMF',
        module_source='Rapprochement MVOLA / PAMF (ecarts generes)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=page_obj.paginator.count,
        export_excel_url=export_excel_url,
        export_pdf_url=export_pdf_url,
    )
    context = {'form': form, 'page_obj': page_obj, 'querystring': querystring, 'meta': meta}

    if is_htmx_request(request):
        return render(request, 'ecarts/partials/liste_table.html', context)

    context.update({'active_tab': 'ecarts', 'active_service': 'mvola'})
    return render(request, 'ecarts/liste_mvola.html', context)


@login_required
def mvola_liste_export(request, format):
    queryset, form = _filtrer_ecarts(request)
    meta = reports.build_meta(
        request,
        titre='Ecarts MVOLA / PAMF',
        module_source='Rapprochement MVOLA / PAMF (ecarts generes)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=queryset.count(),
    )
    return reports.exporter(format, meta, COLONNES_ECARTS, queryset, 'ecarts_mvola')


@login_required
def detail(request, pk):
    ecart = get_object_or_404(
        Ecart.objects.select_related('resultat__transaction_mvola', 'resultat__transaction_pamf'), pk=pk,
    )
    context = {
        'ecart': ecart,
        'transaction_mvola': ecart.resultat.transaction_mvola,
        'transaction_pamf': ecart.resultat.transaction_pamf,
        'commentaire_form': CommentaireForm(),
        'statut_form': ChangerStatutForm(initial={'nouveau_statut': ecart.statut}),
        'piece_jointe_form': PieceJointeForm(),
        'ticket_aspekt_form': TicketAspektForm(),
        'rollback_form': RollbackConfirmeForm(),
        'historique': ecart.historique.select_related('auteur').all(),
        'active_tab': 'ecarts',
        'active_service': 'mvola',
    }
    return render(request, 'ecarts/detail.html', context)


@privilege_required(privileges.TRAITER_ECARTS)
def ajouter_commentaire_vue(request, pk):
    ecart = get_object_or_404(Ecart, pk=pk)
    if request.method == 'POST':
        form = CommentaireForm(request.POST)
        if form.is_valid():
            ajouter_commentaire(ecart, request.user, form.cleaned_data['texte'])
            messages.success(request, 'Commentaire ajoute.')
        else:
            messages.error(request, 'Commentaire invalide.')
    return redirect('ecarts:detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def changer_statut_vue(request, pk):
    ecart = get_object_or_404(Ecart, pk=pk)
    if request.method == 'POST':
        form = ChangerStatutForm(request.POST)
        if form.is_valid():
            resultat = changer_statut(ecart, request.user, form.cleaned_data['nouveau_statut'])
            if resultat:
                messages.success(request, 'Statut mis a jour.')
            else:
                messages.info(request, 'Le statut etait deja a jour.')
        else:
            messages.error(request, 'Statut invalide.')
    return redirect('ecarts:detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def ajouter_piece_jointe_vue(request, pk):
    ecart = get_object_or_404(Ecart, pk=pk)
    if request.method == 'POST':
        form = PieceJointeForm(request.POST, request.FILES)
        if form.is_valid():
            ajouter_piece_jointe(
                ecart, request.user, form.cleaned_data['fichier'], form.cleaned_data.get('commentaire', ''),
            )
            messages.success(request, 'Piece jointe ajoutee.')
        else:
            messages.error(request, 'Piece jointe invalide.')
    return redirect('ecarts:detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def enregistrer_ticket_aspekt_vue(request, pk):
    ecart = get_object_or_404(Ecart, pk=pk)
    if request.method == 'POST':
        form = TicketAspektForm(request.POST)
        if form.is_valid():
            enregistrer_ticket_aspekt(ecart, request.user, form.cleaned_data['reference'])
            messages.success(request, 'Ticket Aspekt enregistre.')
        else:
            messages.error(request, 'Reference de ticket invalide.')
    return redirect('ecarts:detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def confirmer_rollback_vue(request, pk):
    ecart = get_object_or_404(Ecart, pk=pk)
    if request.method == 'POST':
        form = RollbackConfirmeForm(request.POST)
        if form.is_valid():
            confirmer_rollback(ecart, request.user, form.cleaned_data.get('reference', ''))
            messages.success(request, 'Rollback confirme.')
        else:
            messages.error(request, 'Formulaire invalide.')
    return redirect('ecarts:detail', pk=pk)
