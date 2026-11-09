from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import validate_password

from academics.models import Department
from accounts.models import User

from .models import Result, Student


class StudentForm(forms.ModelForm):
    """Creates/edits a Student together with its login account."""

    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(label="Surname", max_length=150)
    other_names = forms.CharField(max_length=150, required=False, help_text="Optional middle name(s)")
    email = forms.EmailField(required=False, help_text="Needed for 'Forgot password' by email.")
    phone = forms.CharField(max_length=20, required=False)
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text="Leave blank to generate a temporary password (shown once after saving). "
                  "The student must change it at first login.",
    )

    class Meta:
        model = Student
        fields = [
            "matric_no", "department", "level", "entry_session", "gender", "date_of_birth",
            "state_of_origin", "address", "guardian_name", "guardian_phone", "status", "photo",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "address": forms.Textarea(attrs={"rows": 2}),
            "photo": forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg"}),
        }

    field_order = ["matric_no", "last_name", "first_name", "other_names", "email", "phone", "password"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            u = self.instance.user
            first, _, other = u.first_name.partition(" ")
            self.initial.update(
                first_name=first, other_names=other, last_name=u.last_name, email=u.email, phone=u.phone
            )
            self.fields["password"].help_text = "Leave blank to keep the current password."
        else:
            self.fields["department"].initial = Department.objects.first()
        self.temp_password = None

    def clean_matric_no(self):
        matric = " ".join(self.cleaned_data["matric_no"].strip().upper().split())
        clash = User.objects.filter(username__iexact=matric)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.user_id)
        if clash.exists():
            raise forms.ValidationError("A user account with this matric number already exists.")
        return matric

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password

    def save(self, commit=True):
        from accounts.security import generate_temp_password

        student = super().save(commit=False)
        user = student.user if student.pk else User(role=User.Role.STUDENT)
        user.username = student.matric_no
        first = self.cleaned_data["first_name"].strip()
        other = self.cleaned_data.get("other_names", "").strip()
        user.first_name = f"{first} {other}".strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.email = self.cleaned_data.get("email", "")
        user.phone = self.cleaned_data.get("phone", "")
        user.is_active = student.status not in (Student.Status.WITHDRAWN,)
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
            user.must_change_password = True
        elif not user.pk:
            self.temp_password = generate_temp_password()
            user.set_password(self.temp_password)
            user.must_change_password = True
        if commit:
            user.save()
            student.user = user
            student.save()
        return student


class ResultEntryForm(forms.ModelForm):
    class Meta:
        model = Result
        fields = ["ca_score", "exam_score"]
        widgets = {
            "ca_score": forms.NumberInput(attrs={"step": "0.5", "min": 0, "max": settings.MAX_CA_SCORE, "class": "form-control form-control-sm"}),
            "exam_score": forms.NumberInput(attrs={"step": "0.5", "min": 0, "max": settings.MAX_EXAM_SCORE, "class": "form-control form-control-sm"}),
        }

    def clean(self):
        data = super().clean()
        ca, exam = data.get("ca_score"), data.get("exam_score")
        if (ca is None) != (exam is None) and not self.errors:
            raise forms.ValidationError("Enter both CA and exam scores, or leave both blank.")
        return data


class CSVUploadForm(forms.Form):
    file = forms.FileField()

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".csv"):
            raise forms.ValidationError("Please upload a .csv file. In Excel use File > Save As > CSV (Comma delimited).")
        if f.size > 2 * 1024 * 1024:
            raise forms.ValidationError("File is too large (max 2 MB).")
        return f


# Kept for the results page (same behaviour as CSVUploadForm).
ResultUploadForm = CSVUploadForm
