"""Emails sent by the system: verification codes and approval notices."""
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.utils import timezone

log = logging.getLogger(__name__)

CODE_MINUTES = 15
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60


def _site_name():
    from academics.models import Institution

    inst = Institution.load()
    return inst.name if inst else "Student Academic Records"


def _send(subject, body, to):
    try:
        send_mail(f"{_site_name()} - {subject}", body, settings.DEFAULT_FROM_EMAIL, to, fail_silently=False)
        return True
    except Exception:  # noqa: BLE001 - email problems must not crash the page
        log.exception("Could not send email to %s", to)
        return False


def seconds_until_resend(user):
    if not user.email_code_sent_at:
        return 0
    wait = RESEND_SECONDS - (timezone.now() - user.email_code_sent_at).total_seconds()
    return max(0, int(wait))


def send_verification_code(user):
    """Create a new 6-digit code, store its hash and email it. Returns True if the email was sent."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = timezone.now()
    user.email_code = make_password(code)
    user.email_code_expires = now + timedelta(minutes=CODE_MINUTES)
    user.email_code_sent_at = now
    user.email_code_attempts = 0
    user.save(update_fields=["email_code", "email_code_expires", "email_code_sent_at", "email_code_attempts"])
    body = (
        f"Hello {user.first_name or user.username},\n\n"
        f"Your verification code is: {code}\n\n"
        f"Enter it on the verification page to activate your account. It expires in {CODE_MINUTES} minutes.\n\n"
        "If you did not create an account, ignore this email."
    )
    return _send("Your verification code", body, [user.email])


def check_verification_code(user, code):
    """Returns (ok, error message)."""
    if not user.email_code or not user.email_code_expires:
        return False, "No code has been sent yet. Click 'Send a new code'."
    if timezone.now() > user.email_code_expires:
        return False, "This code has expired. Click 'Send a new code'."
    if user.email_code_attempts >= MAX_ATTEMPTS:
        return False, "Too many wrong codes. Click 'Send a new code'."
    if not check_password((code or "").strip(), user.email_code):
        user.email_code_attempts += 1
        user.save(update_fields=["email_code_attempts"])
        left = MAX_ATTEMPTS - user.email_code_attempts
        return False, f"That code is not correct. {left} attempt(s) left."
    user.email_verified = True
    user.email_code = ""
    user.email_code_expires = None
    user.save(update_fields=["email_verified", "email_code", "email_code_expires"])
    return True, ""


def notify_admins_new_lecturer(lecturer, approvals_url):
    from .models import User

    admins = list(User.objects.filter(role=User.Role.ADMIN, is_active=True)
                  .exclude(email="").values_list("email", flat=True))
    if admins:
        _send("New lecturer awaiting approval",
              f"{lecturer} ({lecturer.email}, staff ID: {lecturer.staff_id or '-'}) has signed up as a lecturer.\n\n"
              f"Approve or reject the account here: {approvals_url}", admins)


def notify_lecturer_decision(lecturer, approved, login_url):
    if approved:
        body = (f"Hello {lecturer},\n\nYour lecturer account has been approved. "
                f"You can now sign in and use your dashboard: {login_url}")
        _send("Your account has been approved", body, [lecturer.email])
    else:
        body = (f"Hello {lecturer},\n\nYour lecturer sign-up was not approved. "
                "If you think this is a mistake, please contact the department administrator.")
        _send("Your sign-up was not approved", body, [lecturer.email])
