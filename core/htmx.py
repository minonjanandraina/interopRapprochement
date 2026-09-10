def is_htmx_request(request):
    return request.headers.get('HX-Request') == 'true'
