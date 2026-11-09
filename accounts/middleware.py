from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse

_setup_done = False


def setup_is_done():
    """True once at least one administrator account exists."""
    global _setup_done
    if not _setup_done:
        from .models import User

        _setup_done = User.objects.filter(Q(role=User.Role.ADMIN) | Q(is_superuser=True)).exists()
    return _setup_done


class SetupRequiredMiddleware:
    """On a brand-new installation, send every request to the first-run setup page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if not path.startswith(("/setup/", "/static/")) and not setup_is_done():
            return redirect("setup")
        return self.get_response(request)


class ForcePasswordChangeMiddleware:
    """Users given a temporary password must choose their own before doing anything else."""

    ALLOWED = ("password_change", "password_change_done", "logout")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.must_change_password:
            allowed = {reverse(name) for name in self.ALLOWED}
            if request.path not in allowed and not request.path.startswith("/static/"):
                return redirect("password_change")
        return self.get_response(request)
