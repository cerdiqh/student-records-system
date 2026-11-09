from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class User(AbstractUser):
    """System user. Everyone signs up with their own email and has exactly one role."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        LECTURER = "LECTURER", "Lecturer"
        STUDENT = "STUDENT", "Student"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField(max_length=20, blank=True)
    title = models.CharField(max_length=20, blank=True, help_text="e.g. Dr., Prof., Mr., Mrs.")
    staff_id = models.CharField("Staff ID", max_length=30, blank=True, help_text="Lecturer's staff number")

    # Sign-up checks
    email_verified = models.BooleanField(
        default=False, help_text="The user has entered the code sent to their email."
    )
    is_approved = models.BooleanField(
        default=True, help_text="Lecturers must be approved by the administrator before they can work."
    )
    must_change_password = models.BooleanField(
        default=False, help_text="User must set a new password at next login (after a password reset by the admin)."
    )

    # Email verification code (stored hashed, like a password)
    email_code = models.CharField(max_length=128, blank=True, editable=False)
    email_code_expires = models.DateTimeField(null=True, blank=True, editable=False)
    email_code_sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    email_code_attempts = models.PositiveSmallIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(Lower("email"), condition=~Q(email=""), name="unique_user_email"),
        ]

    def __str__(self):
        name = self.get_full_name() or self.username
        return f"{self.title} {name}".strip()

    # Convenience role checks used in views and templates
    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_lecturer(self):
        return self.role == self.Role.LECTURER

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_staff_member(self):
        """May manage all records (the administrator)."""
        return self.is_admin_role
