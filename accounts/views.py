from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from academics.forms import DepartmentForm, InstitutionForm
from academics.models import AcademicSession, Department, Institution

from .decorators import admin_required, staff_required
from .forms import LockoutAuthenticationForm, SetupForm, StaffUserForm
from .middleware import setup_is_done
from .models import User
from .security import generate_temp_password


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class LoginView(auth_views.LoginView):
    form_class = LockoutAuthenticationForm
    redirect_authenticated_user = True


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "registration/password_change.html"
    success_url = reverse_lazy("password_change_done")

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.user.must_change_password:
            self.request.user.must_change_password = False
            self.request.user.save(update_fields=["must_change_password"])
        return response


@staff_required
@require_POST
def reset_password(request, pk):
    """Give a user a new temporary password, shown once to the staff member."""
    target = get_object_or_404(User, pk=pk)
    if not request.user.is_admin_role and not target.is_student:
        raise PermissionDenied("Only an administrator can reset staff passwords.")
    if target.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    temp = generate_temp_password()
    target.set_password(temp)
    target.must_change_password = True
    target.save()
    messages.warning(
        request,
        f"New temporary password for {target.username}: {temp} — give it to the user privately. "
        "They must change it at their next login. This password will not be shown again.",
    )
    return redirect(request.POST.get("next") or "dashboard")


# ---------------------------------------------------------------------------
# First-run setup and institution settings
# ---------------------------------------------------------------------------
def setup(request):
    if setup_is_done():
        return redirect("dashboard")
    form = SetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            Institution(name=d["institution_name"].strip()).save()
            Department.objects.create(name=d["department_name"].strip(), code=d["department_code"].strip().upper(),
                                      faculty=d["faculty"].strip(), final_level=d["final_level"])
            AcademicSession.objects.create(name=d["session_name"], start_date=d["session_start"],
                                           end_date=d["session_end"], is_current=True)
            admin = User(username=d["admin_username"].strip(), first_name=d["admin_first_name"].strip(),
                         last_name=d["admin_last_name"].strip(), email=d["admin_email"], title=d["admin_title"],
                         role=User.Role.ADMIN, is_staff=True, is_superuser=True)
            admin.set_password(d["admin_password"])
            admin.save()
        login(request, admin)
        messages.success(request, "Setup complete. Next: add your lecturers (Staff Accounts), courses, then students.")
        return redirect("dashboard")
    return render(request, "accounts/setup.html", {"form": form})


@admin_required
def institution_settings(request):
    institution = Institution.load() or Institution(name="")
    department = Department.objects.first()
    iform = InstitutionForm(request.POST or None, request.FILES or None, instance=institution, prefix="inst")
    dform = DepartmentForm(request.POST or None, instance=department, prefix="dept")
    if request.method == "POST" and iform.is_valid() and dform.is_valid():
        with transaction.atomic():
            iform.save()
            dform.save()
        messages.success(request, "Institution settings saved.")
        return redirect("institution_settings")
    return render(request, "accounts/institution_settings.html", {"iform": iform, "dform": dform})


def institution_logo(request):
    institution = Institution.load()
    if not institution or not institution.logo:
        raise Http404
    return FileResponse(institution.logo.open("rb"))


# ---------------------------------------------------------------------------
# Staff accounts
# ---------------------------------------------------------------------------
@admin_required
def staff_list(request):
    users = User.objects.exclude(role=User.Role.STUDENT)
    q = request.GET.get("q", "").strip()
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    role = request.GET.get("role")
    if role:
        users = users.filter(role=role)
    page = Paginator(users, 20).get_page(request.GET.get("page"))
    return render(request, "accounts/staff_list.html", {"page": page, "q": q, "roles": User.Role.choices, "role": role})


@admin_required
def staff_form(request, pk=None):
    user = get_object_or_404(User, pk=pk) if pk else None
    if user and user.is_student:
        return redirect("student_edit", pk=user.student_profile.pk)
    form = StaffUserForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        password = form.cleaned_data.get("password")
        temp = None
        if password:
            saved.set_password(password)
            saved.must_change_password = saved.pk != request.user.pk
        elif not saved.pk:
            temp = generate_temp_password()
            saved.set_password(temp)
            saved.must_change_password = True
        saved.is_staff = saved.role == User.Role.ADMIN or saved.is_superuser
        saved.save()
        messages.success(request, f"Account for {saved} saved.")
        if temp:
            messages.warning(request, f"Temporary password for {saved.username}: {temp} — give it to them privately. "
                                      "They must change it at first login. It will not be shown again.")
        return redirect("staff_list")
    return render(request, "form.html", {"form": form, "title": "Edit staff account" if user else "New staff account", "back": "staff_list"})
