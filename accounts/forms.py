from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

from academics.models import AcademicSession, Level

from .models import User
from .security import is_locked_out


class LockoutAuthenticationForm(AuthenticationForm):
    """Login form (email or matric number) that refuses an account after too many failed attempts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email or matric number"
        self.error_messages["invalid_login"] = "Wrong email/matric number or password."

    def clean(self):
        username = self.cleaned_data.get("username")
        if username and is_locked_out(username):
            raise forms.ValidationError(
                f"Too many failed attempts. This account is locked for {settings.LOGIN_LOCKOUT_MINUTES} minutes.",
                code="locked",
            )
        return super().clean()


class PasswordPairMixin(forms.Form):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput,
                                help_text="At least 8 characters. Not only numbers, not a common password.")
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def check_passwords(self, user):
        p1, p2 = self.cleaned_data.get("password1"), self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords do not match.")
        elif p1:
            try:
                validate_password(p1, user)
            except forms.ValidationError as e:
                self.add_error("password1", e)


def email_taken(email):
    return User.objects.filter(email__iexact=email).exists()


class StudentSignupForm(PasswordPairMixin):
    surname = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150)
    other_names = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(help_text="Use your real email. We will send you a code to confirm it.")
    phone = forms.CharField(max_length=20, required=False)
    matric_no = forms.CharField(label="Matric number", max_length=20, help_text="e.g. CSC/2025/001")
    level = forms.TypedChoiceField(choices=Level.choices, coerce=int, label="Current level")
    entry_session = forms.ModelChoiceField(queryset=AcademicSession.objects.all(), label="Year of entry (session)")
    gender = forms.ChoiceField(choices=[("", "---------"), ("M", "Male"), ("F", "Female")])
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    field_order = ["surname", "first_name", "other_names", "email", "phone", "matric_no", "level",
                   "entry_session", "gender", "date_of_birth", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if email_taken(email):
            raise forms.ValidationError("An account with this email already exists. Sign in instead.")
        return email

    def clean_matric_no(self):
        matric = " ".join(self.cleaned_data["matric_no"].strip().upper().split())
        if User.objects.filter(username__iexact=matric).exists():
            raise forms.ValidationError("An account with this matric number already exists. "
                                        "If it is yours, contact the department administrator.")
        return matric

    def clean(self):
        data = super().clean()
        self.check_passwords(User(username=data.get("matric_no", ""), email=data.get("email", ""),
                                  first_name=data.get("first_name", ""), last_name=data.get("surname", "")))
        return data


class LecturerSignupForm(PasswordPairMixin):
    title = forms.ChoiceField(choices=[("", "---------"), ("Mr.", "Mr."), ("Mrs.", "Mrs."), ("Ms.", "Ms."),
                                       ("Dr.", "Dr."), ("Prof.", "Prof."), ("Engr.", "Engr.")], required=False)
    surname = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150)
    email = forms.EmailField(help_text="Use your real (preferably official) email. We will send you a code.")
    phone = forms.CharField(max_length=20, required=False)
    staff_id = forms.CharField(label="Staff ID", max_length=30, required=False,
                               help_text="Helps the administrator confirm you are a real staff member.")

    field_order = ["title", "surname", "first_name", "email", "phone", "staff_id", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if email_taken(email):
            raise forms.ValidationError("An account with this email already exists. Sign in instead.")
        return email

    def clean(self):
        data = super().clean()
        self.check_passwords(User(username=data.get("email", ""), email=data.get("email", ""),
                                  first_name=data.get("first_name", ""), last_name=data.get("surname", "")))
        return data


class StaffUserForm(forms.ModelForm):
    """Administrator creates or edits a lecturer/admin account directly."""

    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text="Leave blank to generate a temporary password (shown once after saving). "
                  "On edit, leave blank to keep the current password.",
    )

    class Meta:
        model = User
        fields = ["title", "first_name", "last_name", "email", "phone", "staff_id", "role", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [c for c in User.Role.choices if c[0] != User.Role.STUDENT]
        for name in ("first_name", "last_name", "email"):
            self.fields[name].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        clash = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password, self.instance)
        return password


class SetupForm(PasswordPairMixin):
    """Administrator sign-up (first visit only): the institution, department, current session and admin."""

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
    admin_email = forms.EmailField(label="Your email", help_text="You will sign in with this email.")

    field_order = ["institution_name", "faculty", "department_name", "department_code", "final_level",
                   "session_name", "session_start", "session_end",
                   "admin_title", "admin_first_name", "admin_last_name", "admin_email", "password1", "password2"]

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
        self.check_passwords(User(username=data.get("admin_email", ""), email=data.get("admin_email", ""),
                                  first_name=data.get("admin_first_name", ""),
                                  last_name=data.get("admin_last_name", "")))
        return data
