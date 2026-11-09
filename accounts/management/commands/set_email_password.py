"""
Safely replace the Gmail App Password stored in .env (typing is hidden), then test it.

    python manage.py set_email_password
"""
import getpass

from django.core.management import call_command
from django.core.management.base import BaseCommand

from .email_check import update_env


class Command(BaseCommand):
    help = "Ask for a new Gmail App Password (hidden), save it in .env and test email."

    def handle(self, *args, **options):
        self.stdout.write("Type the 16-letter Gmail App Password. Nothing appears while you type - that is normal.")
        for _ in range(3):
            raw = getpass.getpass("App Password: ")
            password = "".join(ch for ch in raw if ch.isalpha())  # drop spaces, dots and other stray characters
            if len(password) == 16:
                break
            self.stdout.write(self.style.ERROR(f"That was {len(password)} letters, not 16. Please try again."))
        else:
            self.stdout.write(self.style.ERROR("Stopped. Nothing was changed."))
            return
        update_env({"EMAIL_HOST_PASSWORD": password})
        self.stdout.write(self.style.SUCCESS("Saved in .env. Testing..."))
        # Re-read .env so the test uses the new password.
        from dotenv import load_dotenv
        from django.conf import settings

        load_dotenv(settings.BASE_DIR / ".env", override=True)
        settings.EMAIL_HOST_PASSWORD = password
        call_command("email_check", fix=True)
