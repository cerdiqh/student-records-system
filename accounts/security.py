"""Login brute-force protection and temporary password generation."""
import secrets
import string

from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.cache import cache
from django.dispatch import receiver


def _key(username):
    return f"login-fail:{(username or '').strip().lower()}"


def is_locked_out(username):
    return cache.get(_key(username), 0) >= settings.LOGIN_MAX_ATTEMPTS


@receiver(user_login_failed)
def record_failure(sender, credentials, request=None, **kwargs):
    key = _key(credentials.get("username"))
    attempts = cache.get(key, 0) + 1
    cache.set(key, attempts, settings.LOGIN_LOCKOUT_MINUTES * 60)


@receiver(user_logged_in)
def clear_failures(sender, request, user, **kwargs):
    cache.delete(_key(user.get_username()))


def generate_temp_password(length=10):
    """Readable temporary password: letters + digits + one symbol, no look-alike characters."""
    letters = "".join(c for c in string.ascii_letters if c not in "lIO")
    digits = "23456789"
    while True:
        pw = "".join(secrets.choice(letters + digits) for _ in range(length - 1)) + secrets.choice("@#$%")
        if any(c.isdigit() for c in pw) and any(c.isupper() for c in pw) and any(c.islower() for c in pw):
            return pw
