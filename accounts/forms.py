from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

from academics.models import Level

from .models import User
from .security import is_locked_out


class LockoutAuthenticationForm(AuthenticationForm):
    """Login form that refuses a username after too many failed attempts."""

    def clean(self):
        username = self.cleaned_data.get("username")
        if username and is_locked_out(username):
            raise forms.ValidationError(
                f"Too many failed attempts. This account is locked for {settings.LOGIN_LOCKOUT_MINUTES} minutes.",
                code="locked",
            )
        return super().clean()


class StaffUserForm(forms.ModelForm):
    """Create or edit an Admin / Records Officer / Lecturer account."""

    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text="Leave blank to generate a temporary password (shown once after saving). "
                  "On edit, leave blank to keep the current password.",
    )

    class Meta:
        model = User
        fields = ["title", "first_name", "last_name", "username", "email", "phone", "role", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [c for c in User.Role.choices if c[0] != User.Role.STUDENT]
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password, self.instance)
        return password


class SetupForm(forms.Form):
    """First-run setup: the institution, the department, the first session and the administrator."""

    institution_name = forms.CharField(max_length=200, help_text="e.g. University of Jos")
    faculty = forms.CharField(max_length=150, help_text="e.g. Faculty of Natural Sciences")
    department_name = forms.CharField(max_length=150, help_text="e.g. Computer Science")
    department_code = forms.CharField(max_length=10, help_text="e.g. CSC (used in course codes)")
    final_level = forms.TypedChoiceField(choices=Level.choices, coerce=int, initial=Level.L400,
                                         help_text="Final year of the programme")
    session_name = forms.CharField(label="Current academic session", max_length=9, help_text="e.g. 2025/2026")
    session_start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    session_end = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    admin_title = forms.CharField(label="Your title", max_length=20, required=False)
    admin_first_name = forms.CharField(label="Your first name", max_length=150)
    admin_last_name = forms.CharField(label="Your surname", max_length=150)
    admin_email = forms.EmailField(label="Your email", required=False)
    admin_username = forms.CharField(label="Administrator username", max_length=150)
    admin_password = forms.CharField(label="Password", widget=forms.PasswordInput)
    admin_password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def clean_session_name(self):
        name = self.cleaned_data["session_name"].strip()
        parts = name.split("/")
        if len(parts) != 2 or not all(p.isdigit() and len(p) == 4 for p in parts) or int(parts[1]) != int(parts[0]) + 1:
            raise forms.ValidationError("Use the format YYYY/YYYY, e.g. 2025/2026.")
        return name

    def clean(self):
        data = super().clean()
        if data.get("session_start") and data.get("session_end") and data["session_end"] <= data["session_start"]:
            self.add_error("session_end", "End date must be after start date.")
        p1, p2 = data.get("admin_password"), data.get("admin_password2")
        if p1 and p1 != p2:
            self.add_error("admin_password2", "The passwords do not match.")
        elif p1:
            try:
                validate_password(p1, User(username=data.get("admin_username", ""),
                                           first_name=data.get("admin_first_name", ""),
                                           last_name=data.get("admin_last_name", "")))
            except forms.ValidationError as e:
                self.add_error("admin_password", e)
        return data
