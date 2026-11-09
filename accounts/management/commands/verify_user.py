"""
Emergency tool: mark an account's email as verified (and approved) from the server.

    python manage.py verify_user someone@example.com

Use it only if email sending is not working yet and the administrator is stuck
on the verification page.
"""
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Mark a user's email as verified and the account as approved."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email, **options):
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"No account with email {email}")
        user.email_verified = True
        user.is_approved = True
        user.save(update_fields=["email_verified", "is_approved"])
        self.stdout.write(self.style.SUCCESS(f"{user} ({user.email}) is now verified and approved."))
