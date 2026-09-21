from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def privilege_required(codes):
    """Exige que l'utilisateur connecte dispose d'un des privileges `codes` (cf. user.privileges).

    `codes` peut etre une chaine (un seul privilege) ou une liste de chaines. Un superuser passe
    toujours (cf. User.has_privilege). Sans au moins un des privileges, renvoie un 403 plutot
    qu'une redirection silencieuse : l'utilisateur est bien connecte, il lui manque juste un
    droit qu'un administrateur peut lui accorder via la gestion des roles.
    """
    if isinstance(codes, str):
        codes = [codes]

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not any(request.user.has_privilege(code) for code in codes):
                raise PermissionDenied("Vous n'avez pas le privilege necessaire pour cette action.")
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
