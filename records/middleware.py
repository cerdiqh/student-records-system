"""Stores the current request's user and IP in thread-local storage so model
signals (which have no access to the request) can attribute audit log entries."""
import threading

_local = threading.local()


def get_current_user():
    user = getattr(_local, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def get_current_ip():
    return getattr(_local, "ip", None)


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.user = getattr(request, "user", None)
        _local.ip = client_ip(request)
        try:
            return self.get_response(request)
        finally:
            _local.user = None
            _local.ip = None
