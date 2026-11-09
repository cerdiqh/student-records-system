from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """System user. Every person who logs in has exactly one role."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        REGISTRAR = "REGISTRAR", "Records Officer"
        LECTURER = "LECTURER", "Lecturer"
        STUDENT = "STUDENT", "Student"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField(max_length=20, blank=True)
    title = models.CharField(
        max_length=20, blank=True, help_text="e.g. Dr., Prof., Mr., Mrs."
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text="User must set a new password at next login (set after an account is created or reset).",
    )

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        name = self.get_full_name() or self.username
        return f"{self.title} {name}".strip()

    # Convenience role checks used in views and templates
    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_registrar(self):
        return self.role == self.Role.REGISTRAR

    @property
    def is_lecturer(self):
        return self.role == self.Role.LECTURER

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_staff_member(self):
        """Admin or records officer: may manage all records."""
        return self.is_admin_role or self.is_registrar
