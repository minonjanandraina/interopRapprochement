from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.htmx import is_htmx_request
from core.pagination import paginate

from .forms import FiltreEcartForm
from .models import Ecart


@login_required
def mvola_liste(request):
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

    page_obj, querystring = paginate(request, queryset)
    context = {'form': form, 'page_obj': page_obj, 'querystring': querystring}

    if is_htmx_request(request):
        return render(request, 'ecarts/partials/liste_table.html', context)

    context.update({'active_tab': 'ecarts', 'active_service': 'mvola'})
    return render(request, 'ecarts/liste_mvola.html', context)
