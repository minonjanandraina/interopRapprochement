from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core import reports
from core.htmx import is_htmx_request
from core.pagination import paginate
from transactions.models import ResultatRapprochement, ResultatRapprochementOM, TransactionPamf, TransactionPamfOM
from user import privileges
from user.decorators import privilege_required

from .forms import (
    BulkActionForm,
    ChangerStatutForm,
    CommentaireForm,
    FiltreEcartForm,
    FiltreEcartOMForm,
    PieceJointeForm,
    RollbackConfirmeForm,
    TicketAspektForm,
)
from .models import Ecart, EcartOM
from .services import (
    ajouter_commentaire,
    ajouter_piece_jointe,
    changer_statut,
    confirmer_rollback,
    enregistrer_ticket_aspekt,
    resoudre_doublon_pamf,
)
from . import services_om

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
    filtre_applique = False
    if form.is_valid():
        data = form.cleaned_data
        # Prerequis volontairement plus strict qu'un filtre quelconque (cf. CLAUDE.md) : statut ET
        # action recommandee doivent tous les deux etre choisis pour cibler precisement le lot
        # d'ecarts avant d'autoriser une action en masse.
        filtre_applique = bool(data['statut']) and bool(data['action_recommandee'])
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
        if data['action_recommandee']:
            # action_recommandee est une propriete calculee (cf. Ecart.action_recommandee /
            # ResultatRapprochement.action_recommandee, CLAUDE.md), non stockee en base : on
            # traduit le filtre en conditions equivalentes sur les champs reels plutot que de
            # filtrer en Python, pour rester efficace en base (cf. philosophie bulk du moteur).
            valeur = data['action_recommandee']
            if valeur == ResultatRapprochement.ActionRecommandee.CHOISIR_POSTING:
                queryset = queryset.filter(
                    type_ecart=Ecart.TypeEcart.DOUBLON_PAMF, resultat__transaction_pamf__isnull=True,
                )
            else:
                queryset = queryset.filter(type_ecart=Ecart.TypeEcart.ORPHELINE_MVOLA)
                if valeur == ResultatRapprochement.ActionRecommandee.TICKET_ASPEKT:
                    queryset = queryset.filter(resultat__transaction_pamf__isnull=False)
                else:
                    queryset = queryset.filter(resultat__transaction_pamf__isnull=True)
    return queryset, form, filtre_applique


@login_required
def mvola_liste(request):
    queryset, form, filtre_applique = _filtrer_ecarts(request)
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
    context = {
        'form': form, 'page_obj': page_obj, 'querystring': querystring, 'meta': meta,
        'bulk_form': BulkActionForm(), 'statut_choices': Ecart.Statut.choices,
        'filtre_applique': filtre_applique,
    }

    if is_htmx_request(request):
        return render(request, 'ecarts/partials/liste_table.html', context)

    context.update({'active_tab': 'ecarts', 'active_service': 'mvola'})
    return render(request, 'ecarts/liste_mvola.html', context)


@login_required
def mvola_liste_export(request, format):
    queryset, form, _filtre_applique = _filtrer_ecarts(request)
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
    candidats_pamf = None
    if ecart.action_recommandee == ResultatRapprochement.ActionRecommandee.CHOISIR_POSTING:
        candidats_pamf = TransactionPamf.objects.filter(
            transid_mvola=ecart.transid_mvola, posting_date=ecart.date_transaction,
        )
    context = {
        'ecart': ecart,
        'transaction_mvola': ecart.resultat.transaction_mvola,
        'transaction_pamf': ecart.resultat.transaction_pamf,
        'candidats_pamf': candidats_pamf,
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


@privilege_required(privileges.TRAITER_ECARTS)
def resoudre_doublon_pamf_vue(request, pk):
    ecart = get_object_or_404(Ecart, pk=pk)
    if request.method == 'POST':
        candidat = get_object_or_404(
            TransactionPamf, pk=request.POST.get('transaction_pamf_id'),
            transid_mvola=ecart.transid_mvola, posting_date=ecart.date_transaction,
        )
        resoudre_doublon_pamf(ecart, request.user, candidat)
        messages.success(request, 'Posting PAMF de reference enregistre.')
    return redirect('ecarts:detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def mvola_bulk_action(request):
    """MaJ en masse (statut / commentaire / ticket Aspekt) sur les ecarts coches dans la liste."""
    url = reverse('ecarts:mvola_liste')
    querystring = request.POST.get('_querystring', '')
    if querystring:
        url = f'{url}?{querystring}'

    if request.method != 'POST':
        return redirect(url)

    ids = request.POST.getlist('ecart_ids')
    if not ids:
        messages.error(request, 'Aucun ecart selectionne.')
        return redirect(url)

    form = BulkActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Formulaire de mise a jour en masse invalide.')
        return redirect(url)

    action = form.cleaned_data['action']
    nb = 0
    for ecart in Ecart.objects.filter(pk__in=ids):
        if action == 'statut':
            if changer_statut(ecart, request.user, form.cleaned_data['nouveau_statut']):
                nb += 1
        elif action == 'commentaire':
            ajouter_commentaire(ecart, request.user, form.cleaned_data['texte'])
            nb += 1
        else:
            enregistrer_ticket_aspekt(ecart, request.user, form.cleaned_data['reference'])
            nb += 1
    messages.success(request, f'{nb} ecart(s) mis a jour sur {len(ids)} selectionne(s).')
    return redirect(url)


# --- Orange Money (OM) -------------------------------------------------------------------------
# Miroir des vues MVOLA ci-dessus - cf. CLAUDE.md, Decisions prises (duplication OM).

COLONNES_ECARTS_OM = [
    ('TRANSID', lambda e: e.transid_om),
    ('Date', lambda e: e.date_transaction),
    ('Type', lambda e: e.get_type_ecart_display()),
    ('Montant', lambda e: e.montant),
    ('Action recommandee', lambda e: e.action_recommandee.label if e.action_recommandee else None),
    ('Statut', lambda e: e.get_statut_display()),
    ('Detecte le', lambda e: e.detecte_le),
]


def _filtrer_ecarts_om(request):
    form = FiltreEcartOMForm(request.GET or None)
    queryset = EcartOM.objects.select_related('resultat__transaction_om', 'resultat__transaction_pamf')
    filtre_applique = False
    if form.is_valid():
        data = form.cleaned_data
        # Cf. _filtrer_ecarts (MVOLA) : statut ET action recommandee requis pour cibler le lot avant
        # d'autoriser une action en masse.
        filtre_applique = bool(data['statut']) and bool(data['action_recommandee'])
        if data['date_min']:
            queryset = queryset.filter(date_transaction__gte=data['date_min'])
        if data['date_max']:
            queryset = queryset.filter(date_transaction__lte=data['date_max'])
        if data['transid_om']:
            queryset = queryset.filter(transid_om__icontains=data['transid_om'])
        if data['type_ecart']:
            queryset = queryset.filter(type_ecart=data['type_ecart'])
        if data['statut']:
            queryset = queryset.filter(statut=data['statut'])
        if data['action_recommandee']:
            # Cf. _filtrer_ecarts (MVOLA) : action_recommandee est calculee, non stockee en base.
            valeur = data['action_recommandee']
            if valeur == ResultatRapprochementOM.ActionRecommandee.CHOISIR_POSTING:
                queryset = queryset.filter(
                    type_ecart=EcartOM.TypeEcart.DOUBLON_PAMF, resultat__transaction_pamf__isnull=True,
                )
            else:
                queryset = queryset.filter(type_ecart=EcartOM.TypeEcart.ORPHELINE_OM)
                if valeur == ResultatRapprochementOM.ActionRecommandee.TICKET_ASPEKT:
                    queryset = queryset.filter(resultat__transaction_pamf__isnull=False)
                else:
                    queryset = queryset.filter(resultat__transaction_pamf__isnull=True)
    return queryset, form, filtre_applique


@login_required
def om_liste(request):
    queryset, form, filtre_applique = _filtrer_ecarts_om(request)
    page_obj, querystring = paginate(request, queryset)
    export_excel_url, export_pdf_url = reports.urls_export(request, 'ecarts:om_liste_export')
    meta = reports.build_meta(
        request,
        titre='Ecarts Orange Money / PAMF',
        module_source='Rapprochement Orange Money / PAMF (ecarts generes)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=page_obj.paginator.count,
        export_excel_url=export_excel_url,
        export_pdf_url=export_pdf_url,
    )
    context = {
        'form': form, 'page_obj': page_obj, 'querystring': querystring, 'meta': meta,
        'bulk_form': BulkActionForm(), 'statut_choices': EcartOM.Statut.choices,
        'filtre_applique': filtre_applique,
    }

    if is_htmx_request(request):
        return render(request, 'ecarts/partials/liste_om_table.html', context)

    context.update({'active_tab': 'ecarts', 'active_service': 'om'})
    return render(request, 'ecarts/liste_om.html', context)


@login_required
def om_liste_export(request, format):
    queryset, form, _filtre_applique = _filtrer_ecarts_om(request)
    meta = reports.build_meta(
        request,
        titre='Ecarts Orange Money / PAMF',
        module_source='Rapprochement Orange Money / PAMF (ecarts generes)',
        filtres=reports.decrire_filtres(form),
        nb_lignes=queryset.count(),
    )
    return reports.exporter(format, meta, COLONNES_ECARTS_OM, queryset, 'ecarts_om')


@login_required
def om_detail(request, pk):
    ecart = get_object_or_404(
        EcartOM.objects.select_related('resultat__transaction_om', 'resultat__transaction_pamf'), pk=pk,
    )
    candidats_pamf = None
    if ecart.action_recommandee == ResultatRapprochementOM.ActionRecommandee.CHOISIR_POSTING:
        candidats_pamf = TransactionPamfOM.objects.filter(
            transid_om=ecart.transid_om, posting_date=ecart.date_transaction,
        )
    context = {
        'ecart': ecart,
        'transaction_om': ecart.resultat.transaction_om,
        'transaction_pamf': ecart.resultat.transaction_pamf,
        'candidats_pamf': candidats_pamf,
        'commentaire_form': CommentaireForm(),
        'statut_form': ChangerStatutForm(initial={'nouveau_statut': ecart.statut}),
        'piece_jointe_form': PieceJointeForm(),
        'ticket_aspekt_form': TicketAspektForm(),
        'rollback_form': RollbackConfirmeForm(),
        'historique': ecart.historique.select_related('auteur').all(),
        'active_tab': 'ecarts',
        'active_service': 'om',
    }
    return render(request, 'ecarts/om_detail.html', context)


@privilege_required(privileges.TRAITER_ECARTS)
def om_ajouter_commentaire_vue(request, pk):
    ecart = get_object_or_404(EcartOM, pk=pk)
    if request.method == 'POST':
        form = CommentaireForm(request.POST)
        if form.is_valid():
            services_om.ajouter_commentaire(ecart, request.user, form.cleaned_data['texte'])
            messages.success(request, 'Commentaire ajoute.')
        else:
            messages.error(request, 'Commentaire invalide.')
    return redirect('ecarts:om_detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def om_changer_statut_vue(request, pk):
    ecart = get_object_or_404(EcartOM, pk=pk)
    if request.method == 'POST':
        form = ChangerStatutForm(request.POST)
        if form.is_valid():
            resultat = services_om.changer_statut(ecart, request.user, form.cleaned_data['nouveau_statut'])
            if resultat:
                messages.success(request, 'Statut mis a jour.')
            else:
                messages.info(request, 'Le statut etait deja a jour.')
        else:
            messages.error(request, 'Statut invalide.')
    return redirect('ecarts:om_detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def om_ajouter_piece_jointe_vue(request, pk):
    ecart = get_object_or_404(EcartOM, pk=pk)
    if request.method == 'POST':
        form = PieceJointeForm(request.POST, request.FILES)
        if form.is_valid():
            services_om.ajouter_piece_jointe(
                ecart, request.user, form.cleaned_data['fichier'], form.cleaned_data.get('commentaire', ''),
            )
            messages.success(request, 'Piece jointe ajoutee.')
        else:
            messages.error(request, 'Piece jointe invalide.')
    return redirect('ecarts:om_detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def om_enregistrer_ticket_aspekt_vue(request, pk):
    ecart = get_object_or_404(EcartOM, pk=pk)
    if request.method == 'POST':
        form = TicketAspektForm(request.POST)
        if form.is_valid():
            services_om.enregistrer_ticket_aspekt(ecart, request.user, form.cleaned_data['reference'])
            messages.success(request, 'Ticket Aspekt enregistre.')
        else:
            messages.error(request, 'Reference de ticket invalide.')
    return redirect('ecarts:om_detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def om_confirmer_rollback_vue(request, pk):
    ecart = get_object_or_404(EcartOM, pk=pk)
    if request.method == 'POST':
        form = RollbackConfirmeForm(request.POST)
        if form.is_valid():
            services_om.confirmer_rollback(ecart, request.user, form.cleaned_data.get('reference', ''))
            messages.success(request, 'Rollback confirme.')
        else:
            messages.error(request, 'Formulaire invalide.')
    return redirect('ecarts:om_detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def om_resoudre_doublon_pamf_vue(request, pk):
    ecart = get_object_or_404(EcartOM, pk=pk)
    if request.method == 'POST':
        candidat = get_object_or_404(
            TransactionPamfOM, pk=request.POST.get('transaction_pamf_id'),
            transid_om=ecart.transid_om, posting_date=ecart.date_transaction,
        )
        services_om.resoudre_doublon_pamf(ecart, request.user, candidat)
        messages.success(request, 'Posting PAMF de reference enregistre.')
    return redirect('ecarts:om_detail', pk=pk)


@privilege_required(privileges.TRAITER_ECARTS)
def om_bulk_action(request):
    """Cf. mvola_bulk_action - meme mecanisme pour Orange Money."""
    url = reverse('ecarts:om_liste')
    querystring = request.POST.get('_querystring', '')
    if querystring:
        url = f'{url}?{querystring}'

    if request.method != 'POST':
        return redirect(url)

    ids = request.POST.getlist('ecart_ids')
    if not ids:
        messages.error(request, 'Aucun ecart selectionne.')
        return redirect(url)

    form = BulkActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Formulaire de mise a jour en masse invalide.')
        return redirect(url)

    action = form.cleaned_data['action']
    nb = 0
    for ecart in EcartOM.objects.filter(pk__in=ids):
        if action == 'statut':
            if services_om.changer_statut(ecart, request.user, form.cleaned_data['nouveau_statut']):
                nb += 1
        elif action == 'commentaire':
            services_om.ajouter_commentaire(ecart, request.user, form.cleaned_data['texte'])
            nb += 1
        else:
            services_om.enregistrer_ticket_aspekt(ecart, request.user, form.cleaned_data['reference'])
            nb += 1
    messages.success(request, f'{nb} ecart(s) mis a jour sur {len(ids)} selectionne(s).')
    return redirect(url)
