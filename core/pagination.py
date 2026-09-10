from django.core.paginator import Paginator

PAGE_SIZE = 25


def paginate(request, queryset, page_size=PAGE_SIZE):
    """Pagine `queryset` selon `?page=`. Retourne (page_obj, querystring sans `page`)."""
    page_obj = Paginator(queryset, page_size).get_page(request.GET.get('page'))
    querystring = request.GET.copy()
    querystring.pop('page', None)
    return page_obj, querystring.urlencode()
