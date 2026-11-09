"""
Check that the server can log in to the email account in .env, trying both of
Gmail's connection methods.

    python manage.py email_check          # just report
    python manage.py email_check --fix    # also switch .env to the method that works

Passwords are never printed.
"""
import re
import smtplib
import ssl

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

METHODS = [
    ("587", "STARTTLS (port 587)", {"EMAIL_PORT": "587", "EMAIL_USE_TLS": "True", "EMAIL_USE_SSL": "False"}),
    ("465", "SSL (port 465)", {"EMAIL_PORT": "465", "EMAIL_USE_TLS": "False", "EMAIL_USE_SSL": "True"}),
]


def try_login(host, port, user, password):
    try:
        if port == "465":
            server = smtplib.SMTP_SSL(host, 465, timeout=30, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, 587, timeout=30)
            server.starttls(context=ssl.create_default_context())
        server.login(user, password)
        server.quit()
        return True, "login OK"
    except smtplib.SMTPAuthenticationError as e:
        return False, f"Gmail rejected the address/App Password ({e.smtp_code})"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def update_env(values):
    path = settings.BASE_DIR / ".env"
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        if re.search(rf"^{key}=.*$", text, flags=re.M):
            text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
        else:
            text += f"\n{key}={value}"
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")


class Command(BaseCommand):
    help = "Test the email login with both Gmail methods; --fix switches .env to the working one."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true")

    def handle(self, *args, fix=False, **options):
        host = getattr(settings, "EMAIL_HOST", "")
        user = getattr(settings, "EMAIL_HOST_USER", "")
        password = getattr(settings, "EMAIL_HOST_PASSWORD", "")
        if not host or not user or not password:
            self.stdout.write(self.style.ERROR("EMAIL_HOST, EMAIL_HOST_USER or EMAIL_HOST_PASSWORD is missing in .env"))
            return
        self.stdout.write(f"Account: {user}   Server: {host}   App Password length: {len(password)} (should be 16)")

        working = None
        for port, label, values in METHODS:
            ok, msg = try_login(host, port, user, password)
            style = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(style(f"  {label}: {msg}"))
            if ok and working is None:
                working = (port, label, values)

        if working is None:
            self.stdout.write(self.style.ERROR(
                "\nNeither method works from this server. Send this output to Claude."))
            return

        current = str(getattr(settings, "EMAIL_PORT", ""))
        if working[0] != current:
            if fix:
                update_env(working[2])
                self.stdout.write(self.style.SUCCESS(f"\n.env switched to {working[1]}. Reload the web app."))
            else:
                self.stdout.write(self.style.WARNING(f"\n{working[1]} works. Run again with --fix to use it."))
            return

        send_mail("Email check", "Email from your Student Records system works.",
                  settings.DEFAULT_FROM_EMAIL, [user])
        self.stdout.write(self.style.SUCCESS(f"\nTest email sent to {user}. Email is working."))
