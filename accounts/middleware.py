from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse

_setup_done = False


def setup_is_done():
    """True once the administrator account exists."""
    global _setup_done
    if not _setup_done:
        from .models import User

        _setup_done = User.objects.filter(Q(role=User.Role.ADMIN) | Q(is_superuser=True)).exists()
    return _setup_done


class SetupRequiredMiddleware:
    """On a brand-new installation, send every request to the administrator sign-up page."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(("/setup/", "/static/")) and not setup_is_done():
            return redirect("setup")
        return self.get_response(request)


class AccountStatusMiddleware:
    """
    Keeps signed-in users on the right page until their account is ready:
      1. email not verified        -> enter the 6-digit code
      2. lecturer not yet approved -> waiting for approval page
      3. temporary password        -> choose a new password
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not request.path.startswith("/static/"):
            path = request.path
            always_ok = {reverse("logout")}
            if not user.email_verified:
                target = "verify_email"
            elif not user.is_approved:
                target = "pending_approval"
            elif user.must_change_password:
                target = "password_change"
                always_ok.add(reverse("password_change_done"))
            else:
                target = None
            if target and path != reverse(target) and path not in always_ok:
                return redirect(target)
        return self.get_response(request)
