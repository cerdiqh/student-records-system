from django import forms

from accounts.models import User

from .models import AcademicSession, Course, Department, Institution


class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ["name", "address", "email", "phone", "registrar_name", "logo"]

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "size"):
            if logo.size > 1024 * 1024:
                raise forms.ValidationError("Logo is too large (max 1 MB).")
            if not logo.name.lower().endswith((".png", ".jpg", ".jpeg")):
                raise forms.ValidationError("Upload a PNG or JPG image.")
        return logo


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "code", "faculty", "final_level", "head"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["head"].queryset = User.objects.filter(role=User.Role.LECTURER, is_active=True)
        self.fields["head"].label = "Head of Department"


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["code", "title", "units", "level", "semester", "department", "lecturer", "is_elective", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lecturer"].queryset = User.objects.filter(role=User.Role.LECTURER, is_active=True)
        if not self.instance.pk:
            self.fields["department"].initial = Department.objects.first()

    def clean_code(self):
        return " ".join(self.cleaned_data["code"].upper().split())


class AcademicSessionForm(forms.ModelForm):
    class Meta:
        model = AcademicSession
        fields = ["name", "start_date", "end_date", "is_current", "current_semester", "registration_open"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        parts = name.split("/")
        if len(parts) != 2 or not all(p.isdigit() and len(p) == 4 for p in parts) or int(parts[1]) != int(parts[0]) + 1:
            raise forms.ValidationError("Use the format YYYY/YYYY, e.g. 2025/2026.")
        return name
