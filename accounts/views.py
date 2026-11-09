from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST

from academics.forms import DepartmentForm, InstitutionForm
from academics.models import AcademicSession, Department, Institution
from records.models import AuditLog, Student

from . import emails
from .decorators import admin_required
from .forms import LecturerSignupForm, LockoutAuthenticationForm, SetupForm, StaffUserForm, StudentSignupForm
from .middleware import setup_is_done
from .models import User
from .security import generate_temp_password

BACKEND = "accounts.backends.EmailOrUsernameBackend"


def _email_is_real():
    """False when emails are only printed to the server console (no SMTP configured)."""
    return settings.EMAIL_BACKEND.endswith("smtp.EmailBackend")


# ---------------------------------------------------------------------------
# Sign in / passwords
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


@admin_required
@require_POST
def reset_password(request, pk):
    """Give a user a new temporary password, shown once to the administrator."""
    target = get_object_or_404(User, pk=pk)
    if target.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    temp = generate_temp_password()
    target.set_password(temp)
    target.must_change_password = True
    target.save()
    messages.warning(
        request,
        f"New temporary password for {target.email or target.username}: {temp} — give it to the user privately. "
        "They must change it at their next sign-in. This password will not be shown again.",
    )
    return redirect(request.POST.get("next") or "dashboard")


# ---------------------------------------------------------------------------
# Sign up
# ---------------------------------------------------------------------------
def setup(request):
    """Administrator sign-up. Only available until the first administrator exists."""
    if setup_is_done():
        return redirect("signup")
    form = SetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            Institution(name=d["institution_name"].strip()).save()
            Department.objects.create(name=d["department_name"].strip(), code=d["department_code"].strip().upper(),
                                      faculty=d["faculty"].strip(), final_level=d["final_level"])
            AcademicSession.objects.create(name=d["session_name"], start_date=d["session_start"],
                                           end_date=d["session_end"], is_current=True)
            admin = User(username=d["admin_email"].lower(), email=d["admin_email"].lower(),
                         first_name=d["admin_first_name"].strip(), last_name=d["admin_last_name"].strip(),
                         title=d["admin_title"], role=User.Role.ADMIN, is_staff=True, is_superuser=True)
            admin.set_password(d["password1"])
            admin.save()
        login(request, admin, backend=BACKEND)
        emails.send_verification_code(admin)
        return redirect("verify_email")
    return render(request, "accounts/setup.html", {"form": form})


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "accounts/signup_choice.html")


def signup_student(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    department = Department.objects.first()
    if AcademicSession.objects.count() == 0 or department is None:
        messages.error(request, "Student sign-up is not open yet. Please try again later.")
        return redirect("login")
    form = StudentSignupForm(request.POST or None, initial={"entry_session": AcademicSession.get_current()})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            user = User(username=d["matric_no"], email=d["email"], role=User.Role.STUDENT,
                        first_name=f"{d['first_name'].strip()} {d['other_names'].strip()}".strip(),
                        last_name=d["surname"].strip(), phone=d["phone"], is_approved=True)
            user.set_password(d["password1"])
            user.save()
            Student.objects.create(user=user, matric_no=d["matric_no"], department=department, level=d["level"],
                                   entry_session=d["entry_session"], gender=d["gender"],
                                   date_of_birth=d["date_of_birth"])
        login(request, user, backend=BACKEND)
        emails.send_verification_code(user)
        return redirect("verify_email")
    return render(request, "accounts/signup_form.html", {"form": form, "kind": "Student"})


def signup_lecturer(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = LecturerSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        user = User(username=d["email"], email=d["email"], role=User.Role.LECTURER, title=d["title"],
                    first_name=d["first_name"].strip(), last_name=d["surname"].strip(), phone=d["phone"],
                    staff_id=d["staff_id"].strip(), is_approved=False)
        user.set_password(d["password1"])
        user.save()
        login(request, user, backend=BACKEND)
        emails.send_verification_code(user)
        return redirect("verify_email")
    return render(request, "accounts/signup_form.html", {"form": form, "kind": "Lecturer"})


@login_required
def verify_email(request):
    user = request.user
    if user.email_verified:
        return redirect("dashboard")
    if request.method == "POST":
        if request.POST.get("action") == "resend":
            wait = emails.seconds_until_resend(user)
            if wait:
                messages.warning(request, f"Please wait {wait} seconds before asking for another code.")
            elif emails.send_verification_code(user):
                messages.success(request, f"A new code has been sent to {user.email}.")
            else:
                messages.error(request, "We could not send the email right now. Please try again later "
                                        "or contact the department administrator.")
            return redirect("verify_email")
        ok, error = emails.check_verification_code(user, request.POST.get("code", ""))
        if ok:
            if user.is_lecturer and not user.is_approved:
                emails.notify_admins_new_lecturer(user, request.build_absolute_uri(reverse("user_approvals")))
                return redirect("pending_approval")
            messages.success(request, "Your email is confirmed. Welcome!")
            return redirect("dashboard")
        messages.error(request, error)
    return render(request, "accounts/verify_email.html", {
        "email_is_real": _email_is_real(),
        "resend_wait": emails.seconds_until_resend(user),
    })


@login_required
def pending_approval(request):
    if request.user.is_approved:
        return redirect("dashboard")
    return render(request, "accounts/pending_approval.html")


# ---------------------------------------------------------------------------
# Administrator: approve lecturers, manage staff accounts, settings
# ---------------------------------------------------------------------------
@admin_required
def user_approvals(request):
    pending = User.objects.filter(role=User.Role.LECTURER, is_approved=False, is_active=True).order_by("date_joined")
    return render(request, "accounts/approvals.html", {"pending": pending})


@admin_required
@require_POST
def approve_user(request, pk):
    lecturer = get_object_or_404(User, pk=pk, role=User.Role.LECTURER)
    login_url = request.build_absolute_uri(reverse("login"))
    if request.POST.get("action") == "approve":
        lecturer.is_approved = True
        lecturer.save(update_fields=["is_approved"])
        AuditLog.objects.create(user=request.user, action=AuditLog.Action.APPROVE, model_name="User",
                                object_id=str(lecturer.pk), object_repr=f"Approved lecturer {lecturer} ({lecturer.email})")
        emails.notify_lecturer_decision(lecturer, True, login_url)
        messages.success(request, f"{lecturer} can now sign in as a lecturer.")
    else:
        lecturer.is_active = False
        lecturer.save(update_fields=["is_active"])
        AuditLog.objects.create(user=request.user, action=AuditLog.Action.UPDATE, model_name="User",
                                object_id=str(lecturer.pk), object_repr=f"Rejected lecturer sign-up {lecturer} ({lecturer.email})")
        emails.notify_lecturer_decision(lecturer, False, login_url)
        messages.info(request, f"Sign-up from {lecturer} was rejected and the account disabled.")
    return redirect("user_approvals")


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
    return render(request, "accounts/institution_settings.html", {
        "iform": iform, "dform": dform, "email_is_real": _email_is_real(),
        "signup_url": request.build_absolute_uri(reverse("signup")),
    })


def institution_logo(request):
    institution = Institution.load()
    if not institution or not institution.logo:
        raise Http404
    return FileResponse(institution.logo.open("rb"))


@admin_required
def staff_list(request):
    users = User.objects.exclude(role=User.Role.STUDENT)
    q = request.GET.get("q", "").strip()
    if q:
        users = users.filter(
            Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(staff_id__icontains=q)
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
        saved.username = saved.email
        password = form.cleaned_data.get("password")
        temp = None
        if password:
            saved.set_password(password)
            saved.must_change_password = saved.pk != request.user.pk
        elif not saved.pk:
            temp = generate_temp_password()
            saved.set_password(temp)
            saved.must_change_password = True
        if not saved.pk:
            saved.is_approved = True  # created by the administrator, so already approved
        saved.is_staff = saved.role == User.Role.ADMIN or saved.is_superuser
        saved.save()
        messages.success(request, f"Account for {saved} saved.")
        if temp:
            messages.warning(request, f"Temporary password for {saved.email}: {temp} — give it to them privately. "
                                      "They confirm their email and choose a new password at first sign-in. "
                                      "It will not be shown again.")
        return redirect("staff_list")
    return render(request, "form.html", {"form": form, "title": "Edit staff account" if user else "New staff account", "back": "staff_list"})
