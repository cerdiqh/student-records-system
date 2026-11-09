from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import User


class StaffUserForm(forms.ModelForm):
    """Create or edit an Admin / Records Officer / Lecturer account."""

    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text="Required for new accounts. Leave blank to keep the current password.",
    )

    class Meta:
        model = User
        fields = ["title", "first_name", "last_name", "username", "email", "phone", "role", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [
            c for c in User.Role.choices if c[0] != User.Role.STUDENT
        ]
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not self.instance.pk and not password:
            raise forms.ValidationError("A password is required for a new account.")
        if password:
            validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user
