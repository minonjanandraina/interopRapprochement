from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def privilege_required(code):
    """Exige que l'utilisateur connecte dispose du privilege `code` (cf. user.privileges).

    Un superuser passe toujours (cf. User.has_privilege). Sans le privilege, renvoie un 403
    plutot qu'une redirection silencieuse : l'utilisateur est bien connecte, il lui manque juste
    un droit qu'un administrateur peut lui accorder via la gestion des roles.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not request.user.has_privilege(code):
                raise PermissionDenied("Vous n'avez pas le privilege necessaire pour cette action.")
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
