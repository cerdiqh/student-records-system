import csv
import io
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.core import management
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required, lecturer_or_staff_required, staff_required
from accounts.models import User
from academics.models import AcademicSession, Course, Department, Level

from . import importers
from .forms import CSVUploadForm, ResultEntryForm, ResultUploadForm, StudentForm
from .models import AuditLog, Registration, Result, Student
from .transcript import build_transcript_pdf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _can_view_student(user, student):
    return user.is_staff_member or (user.is_student and student.user_id == user.pk)


def _can_manage_course_results(user, course):
    return user.is_staff_member or (user.is_lecturer and course.lecturer_id == user.pk)


def _selected_session(request):
    sid = request.GET.get("session") or request.POST.get("session")
    if sid:
        return get_object_or_404(AcademicSession, pk=sid)
    session = AcademicSession.get_current()
    if session is None:
        raise PermissionDenied("No current academic session has been set up yet.")
    return session


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@login_required
def dashboard(request):
    user = request.user
    session = AcademicSession.get_current()
    ctx = {"session": session}

    if user.is_staff_member:
        ctx.update(
            total_students=Student.objects.filter(status=Student.Status.ACTIVE).count(),
            total_courses=Course.objects.filter(is_active=True).count(),
            total_lecturers=User.objects.filter(role=User.Role.LECTURER, is_active=True).count(),
            registrations=Registration.objects.filter(session=session).count() if session else 0,
            by_level=Student.objects.filter(status=Student.Status.ACTIVE)
            .values("level").annotate(n=Count("id")).order_by("level"),
            pending=Result.objects.filter(status=Result.Status.SUBMITTED)
            .values("registration__course__id", "registration__course__code",
                    "registration__course__title", "registration__session__id",
                    "registration__session__name")
            .annotate(n=Count("id")).order_by("registration__course__code"),
            recent_logs=AuditLog.objects.select_related("user")[:8],
        )
        ctx["needs_setup"] = not (ctx["total_lecturers"] and ctx["total_courses"] and ctx["total_students"])
        return render(request, "records/dashboard_staff.html", ctx)

    if user.is_lecturer:
        courses = Course.objects.filter(lecturer=user, is_active=True).annotate(
            enrolled=Count("registrations", filter=Q(registrations__session=session)),
            submitted=Count("registrations__result", filter=Q(
                registrations__session=session,
                registrations__result__status__in=[Result.Status.SUBMITTED, Result.Status.APPROVED])),
        )
        ctx["courses"] = courses
        return render(request, "records/dashboard_lecturer.html", ctx)

    if user.is_student:
        student = getattr(user, "student_profile", None)
        if student is None:
            raise PermissionDenied("Your account is not linked to a student record. Contact the records office.")
        current_regs = Registration.objects.filter(student=student, session=session).select_related("course", "result") if session else []
        ctx.update(
            student=student,
            cgpa=student.cgpa(),
            degree_class=student.degree_class(),
            units_passed=student.total_units_passed(),
            current_regs=current_regs,
            current_units=sum(r.course.units for r in current_regs),
        )
        return render(request, "records/dashboard_student.html", ctx)

    raise PermissionDenied


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
@staff_required
def student_list(request):
    students = Student.objects.select_related("user", "department")
    q = request.GET.get("q", "").strip()
    if q:
        students = students.filter(
            Q(matric_no__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
        )
    level = request.GET.get("level")
    if level:
        students = students.filter(level=level)
    status = request.GET.get("status")
    if status:
        students = students.filter(status=status)
    page = Paginator(students, 25).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "records/student_list.html", {
        "page": page, "q": q, "level": level, "status": status,
        "levels": Level.choices, "statuses": Student.Status.choices, "querystring": query.urlencode(),
    })


@staff_required
def student_form(request, pk=None):
    student = get_object_or_404(Student, pk=pk) if pk else None
    form = StudentForm(request.POST or None, request.FILES or None, instance=student)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved = form.save()
        messages.success(request, f"Record for {saved.full_name} ({saved.matric_no}) saved.")
        if form.temp_password:
            messages.warning(request, f"Temporary password for {saved.matric_no}: {form.temp_password} — give it to the "
                                      "student privately. They must change it at first login. It will not be shown again.")
        return redirect("student_detail", pk=saved.pk)
    title = f"Edit {student.matric_no}" if student else "Register new student"
    return render(request, "form.html", {"form": form, "title": title, "back": "student_list"})


@login_required
def student_detail(request, pk):
    student = get_object_or_404(Student.objects.select_related("user", "department", "entry_session"), pk=pk)
    if not _can_view_student(request.user, student):
        raise PermissionDenied
    pending = Registration.objects.filter(student=student).exclude(
        result__status=Result.Status.APPROVED
    ).select_related("course", "session", "result")
    return render(request, "records/student_detail.html", {
        "student": student,
        "semesters": student.semester_breakdown(),
        "cgpa": student.cgpa(),
        "degree_class": student.degree_class(),
        "units_passed": student.total_units_passed(),
        "pending": pending,
    })


@login_required
def my_record(request):
    student = getattr(request.user, "student_profile", None)
    if student is None:
        return redirect("dashboard")
    return redirect("student_detail", pk=student.pk)


@admin_required
@require_POST
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if Result.objects.filter(registration__student=student, status=Result.Status.APPROVED).exists():
        messages.error(request, "This student has approved results. Change their status to Withdrawn instead of deleting.")
        return redirect("student_detail", pk=pk)
    name = str(student)
    with transaction.atomic():
        user = student.user
        student.delete()
        user.delete()
    messages.success(request, f"Deleted {name}.")
    return redirect("student_list")


@staff_required
def export_students(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="students.csv"'
    writer = csv.writer(response)
    writer.writerow(["Matric No", "Surname", "Other Names", "Gender", "Level", "Status", "Email", "Phone", "CGPA"])
    for s in Student.objects.select_related("user"):
        writer.writerow([s.matric_no, s.user.last_name, s.user.first_name, s.get_gender_display(),
                         s.level, s.get_status_display(), s.user.email, s.user.phone, s.cgpa()])
    return response


# ---------------------------------------------------------------------------
# Course registration
# ---------------------------------------------------------------------------
@login_required
def register_courses(request, pk=None):
    user = request.user
    if pk is not None:
        if not user.is_staff_member:
            raise PermissionDenied
        student = get_object_or_404(Student, pk=pk)
    else:
        student = getattr(user, "student_profile", None)
        if student is None:
            raise PermissionDenied
    session = AcademicSession.get_current()
    if session is None:
        messages.error(request, "No current academic session. Contact the records office.")
        return redirect("dashboard")
    semester = session.current_semester
    can_edit = user.is_staff_member or (session.registration_open and student.status == Student.Status.ACTIVE)

    registered = Registration.objects.filter(
        student=student, session=session, course__semester=semester
    ).select_related("course", "result")
    registered_ids = {r.course_id for r in registered}

    # Courses for the student's level this semester, plus failed courses to carry over.
    passed_ids = set(
        Result.objects.filter(registration__student=student, status=Result.Status.APPROVED, grade_point__gt=0)
        .values_list("registration__course_id", flat=True)
    )
    failed_ids = set(
        Result.objects.filter(registration__student=student, status=Result.Status.APPROVED, grade_point=0)
        .values_list("registration__course_id", flat=True)
    ) - passed_ids
    available = Course.objects.filter(is_active=True, semester=semester).filter(
        Q(level=student.level) | Q(pk__in=failed_ids)
    ).exclude(pk__in=registered_ids | passed_ids).order_by("level", "code")

    current_units = sum(r.course.units for r in registered)

    if request.method == "POST":
        if not can_edit:
            messages.error(request, "Course registration is closed.")
            return redirect(request.path)
        action = request.POST.get("action")
        if action == "drop":
            reg = get_object_or_404(Registration, pk=request.POST.get("registration"), student=student, session=session)
            if hasattr(reg, "result") and (reg.result.status != Result.Status.DRAFT or reg.result.is_complete):
                messages.error(request, f"{reg.course.code} already has a result and cannot be dropped.")
            else:
                reg.delete()
                messages.success(request, f"Dropped {reg.course.code}.")
            return redirect(request.path)

        chosen = list(available.filter(pk__in=request.POST.getlist("courses")))
        new_units = sum(c.units for c in chosen)
        if not chosen:
            messages.warning(request, "Select at least one course.")
        elif current_units + new_units > settings.MAX_UNITS_PER_SEMESTER:
            messages.error(
                request,
                f"That would be {current_units + new_units} units. The maximum is {settings.MAX_UNITS_PER_SEMESTER} per semester.",
            )
        else:
            with transaction.atomic():
                for c in chosen:
                    Registration.objects.create(student=student, course=c, session=session)
            messages.success(request, f"Registered {len(chosen)} course(s), {new_units} units.")
        return redirect(request.path)

    return render(request, "records/register_courses.html", {
        "student": student, "session": session, "semester": session.get_current_semester_display(),
        "registered": registered, "available": available, "failed_ids": failed_ids,
        "current_units": current_units, "max_units": settings.MAX_UNITS_PER_SEMESTER, "can_edit": can_edit,
    })


# ---------------------------------------------------------------------------
# Results entry (lecturers) and approval (records office)
# ---------------------------------------------------------------------------
@lecturer_or_staff_required
def course_results(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not _can_manage_course_results(request.user, course):
        raise PermissionDenied
    session = _selected_session(request)
    regs = Registration.objects.filter(course=course, session=session).select_related("student__user")
    for reg in regs:
        if not hasattr(reg, "result"):
            Result.objects.create(registration=reg, entered_by=request.user)
    results = list(
        Result.objects.filter(registration__in=regs).select_related("registration__student__user")
        .order_by("registration__student__matric_no")
    )
    rows = [(r, ResultEntryForm(request.POST or None, instance=r, prefix=f"r{r.pk}")) for r in results]

    if request.method == "POST":
        action = request.POST.get("action", "save")
        editable = [(r, f) for r, f in rows if r.status != Result.Status.APPROVED]
        if all(f.is_valid() for _, f in editable):
            submitted = missing = 0
            with transaction.atomic():
                for r, f in editable:
                    obj = f.save(commit=False)
                    obj.entered_by = request.user
                    if action == "submit":
                        if obj.is_complete:
                            obj.status = Result.Status.SUBMITTED
                            submitted += 1
                        else:
                            missing += 1
                    obj.save()
            if action == "submit":
                messages.success(request, f"{submitted} result(s) for {course.code} submitted to the records office for approval.")
                if missing:
                    messages.warning(request, f"{missing} student(s) have no scores yet and were kept as draft.")
            else:
                messages.success(request, "Scores saved as draft.")
            return redirect(f"{request.path}?session={session.pk}")
        messages.error(request, "Some scores are invalid. Check the highlighted rows.")

    # Use the saved total (an invalid form may have put unsaved scores on the instance).
    entered = [r for r in results if r.total is not None]
    stats = {
        "count": len(results),
        "entered": len(entered),
        "passed": sum(1 for r in entered if r.grade_point > 0),
        "average": (sum(r.total for r in entered) / len(entered)).quantize(Decimal("0.01")) if entered else "-",
        "grades": {g: sum(1 for r in entered if r.grade == g) for _, g, _ in settings.GRADING_SCALE},
    }
    return render(request, "records/course_results.html", {
        "course": course, "session": session, "rows": rows, "stats": stats,
        "sessions": AcademicSession.objects.all(), "upload_form": ResultUploadForm(),
        "max_ca": settings.MAX_CA_SCORE, "max_exam": settings.MAX_EXAM_SCORE,
        "has_editable": any(r.status != Result.Status.APPROVED for r in results),
    })


@lecturer_or_staff_required
@require_POST
def course_results_upload(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not _can_manage_course_results(request.user, course):
        raise PermissionDenied
    session = _selected_session(request)
    back = redirect(f"{reverse('course_results', args=[course.pk])}?session={session.pk}")
    form = ResultUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        for err in form.errors.get("file", []):
            messages.error(request, err)
        return back

    text = io.TextIOWrapper(form.cleaned_data["file"].file, encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(text)
    headers = {h.strip().lower() for h in (reader.fieldnames or [])}
    if not {"matric_no", "ca_score", "exam_score"} <= headers:
        messages.error(request, "CSV must have the columns: matric_no, ca_score, exam_score")
        return back

    results = {
        r.registration.student.matric_no.upper(): r
        for r in Result.objects.filter(registration__course=course, registration__session=session)
        .select_related("registration__student")
    }
    updated, errors = 0, []
    with transaction.atomic():
        for line, raw in enumerate(reader, start=2):
            row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            matric = row.get("matric_no", "").upper()
            if not matric:
                continue
            result = results.get(matric)
            if result is None:
                errors.append(f"Row {line}: {matric} is not registered for {course.code} in {session}.")
                continue
            if result.status == Result.Status.APPROVED:
                errors.append(f"Row {line}: {matric} result is already approved and locked.")
                continue
            if not row.get("ca_score") and not row.get("exam_score"):
                continue  # nothing entered for this student yet
            try:
                ca, exam = Decimal(row["ca_score"]), Decimal(row["exam_score"])
            except (InvalidOperation, KeyError):
                errors.append(f"Row {line}: enter both CA and exam scores as numbers.")
                continue
            if not (0 <= ca <= settings.MAX_CA_SCORE and 0 <= exam <= settings.MAX_EXAM_SCORE):
                errors.append(f"Row {line}: CA must be 0-{settings.MAX_CA_SCORE} and exam 0-{settings.MAX_EXAM_SCORE}.")
                continue
            result.ca_score, result.exam_score, result.entered_by = ca, exam, request.user
            result.save()
            updated += 1
    messages.success(request, f"Uploaded scores for {updated} student(s).")
    for e in errors[:15]:
        messages.warning(request, e)
    if len(errors) > 15:
        messages.warning(request, f"...and {len(errors) - 15} more problems.")
    return back


@lecturer_or_staff_required
def course_results_csv(request, pk):
    """Download the score sheet as CSV (also serves as the upload template)."""
    course = get_object_or_404(Course, pk=pk)
    if not _can_manage_course_results(request.user, course):
        raise PermissionDenied
    session = _selected_session(request)
    response = HttpResponse(content_type="text/csv")
    fname = f"{course.code.replace(' ', '')}_{session.name.replace('/', '-')}_results.csv"
    response["Content-Disposition"] = f'attachment; filename="{fname}"'
    writer = csv.writer(response)
    writer.writerow(["matric_no", "name", "ca_score", "exam_score", "total", "grade"])
    regs = Registration.objects.filter(course=course, session=session).select_related("student__user").order_by("student__matric_no")
    for reg in regs:
        r = getattr(reg, "result", None)
        done = r is not None and r.is_complete
        writer.writerow([reg.student.matric_no, reg.student.full_name,
                         r.ca_score if done else "", r.exam_score if done else "",
                         r.total if done else "", r.grade if done else ""])
    return response


@staff_required
def approval_list(request):
    pending = (
        Result.objects.filter(status=Result.Status.SUBMITTED)
        .values("registration__course__id", "registration__course__code", "registration__course__title",
                "registration__course__lecturer__first_name", "registration__course__lecturer__last_name",
                "registration__session__id", "registration__session__name")
        .annotate(n=Count("id"))
        .order_by("registration__session__name", "registration__course__code")
    )
    return render(request, "records/approval_list.html", {"pending": pending})


@staff_required
@require_POST
def approve_results(request, pk):
    course = get_object_or_404(Course, pk=pk)
    session = _selected_session(request)
    action = request.POST.get("action")
    qs = Result.objects.filter(registration__course=course, registration__session=session)
    if action == "approve":
        to_approve = list(qs.filter(status=Result.Status.SUBMITTED))
        now = timezone.now()
        with transaction.atomic():
            for r in to_approve:
                r.status, r.approved_by, r.approved_at = Result.Status.APPROVED, request.user, now
                r.save()
            AuditLog.objects.create(
                user=request.user, action=AuditLog.Action.APPROVE, model_name="Result",
                object_repr=f"{course.code} {session} ({len(to_approve)} results)",
            )
        messages.success(request, f"Approved {len(to_approve)} result(s) for {course.code}.")
    elif action == "return":
        n = 0
        for r in qs.filter(status=Result.Status.SUBMITTED):
            r.status = Result.Status.DRAFT
            r.save()
            n += 1
        messages.info(request, f"Returned {n} result(s) for {course.code} to the lecturer for correction.")
    elif action == "reopen":
        if not request.user.is_admin_role:
            raise PermissionDenied
        n = 0
        for r in qs.filter(status=Result.Status.APPROVED):
            r.status, r.approved_by, r.approved_at = Result.Status.DRAFT, None, None
            r.save()
            n += 1
        messages.warning(request, f"Unlocked {n} approved result(s) for {course.code}.")
    return redirect(request.POST.get("next") or "approval_list")


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------
@login_required
def transcript(request, pk):
    student = get_object_or_404(Student.objects.select_related("user", "department"), pk=pk)
    if not _can_view_student(request.user, student):
        raise PermissionDenied
    return render(request, "records/transcript.html", {
        "student": student, "semesters": student.semester_breakdown(),
        "cgpa": student.cgpa(), "degree_class": student.degree_class(),
        "units_passed": student.total_units_passed(), "generated": timezone.localtime(),
        "grading_scale": settings.GRADING_SCALE,
    })


@login_required
def transcript_pdf(request, pk):
    student = get_object_or_404(Student.objects.select_related("user", "department"), pk=pk)
    if not _can_view_student(request.user, student):
        raise PermissionDenied
    pdf = build_transcript_pdf(student)
    response = HttpResponse(pdf, content_type="application/pdf")
    fname = f"transcript_{student.matric_no.replace('/', '-')}.pdf"
    response["Content-Disposition"] = f'inline; filename="{fname}"'
    return response


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
@admin_required
def audit_log(request):
    logs = AuditLog.objects.select_related("user")
    q = request.GET.get("q", "").strip()
    if q:
        logs = logs.filter(Q(object_repr__icontains=q) | Q(changes__icontains=q) | Q(user__username__icontains=q))
    action = request.GET.get("action")
    if action:
        logs = logs.filter(action=action)
    page = Paginator(logs, 30).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "records/audit_log.html", {
        "page": page, "q": q, "action": action, "actions": AuditLog.Action.choices, "querystring": query.urlencode(),
    })


# ---------------------------------------------------------------------------
# Bulk import (real data from CSV / Excel)
# ---------------------------------------------------------------------------
def _csv_template(filename, columns, example_rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(columns)
    writer.writerows(example_rows)
    return response


@staff_required
def student_import(request):
    department = Department.objects.first()
    form = CSVUploadForm(request.POST or None, request.FILES or None)
    errors = []
    if request.method == "POST" and form.is_valid():
        created, errors = importers.import_students(form.cleaned_data["file"], department)
        if created:
            request.session["import_credentials"] = created
            messages.success(request, f"Imported {len(created)} student(s). Download their login slips now — "
                                      "the temporary passwords are shown only once.")
            return render(request, "records/import_done.html", {"created": created, "kind": "students"})
    return render(request, "records/import.html", {
        "form": form, "errors": errors, "kind": "students", "title": "Import students",
        "template_url": reverse("student_import_template"), "columns": importers.STUDENT_COLUMNS,
        "required": importers.STUDENT_REQUIRED, "sessions": AcademicSession.objects.all(),
    })


@staff_required
def student_import_template(request):
    session = AcademicSession.get_current()
    s = session.name if session else "2025/2026"
    return _csv_template("students_template.csv", importers.STUDENT_COLUMNS, [
        ["CSC/2025/001", "Okafor", "Chinedu", "Emeka", "M", "100", s, "chinedu@example.com", "08012345678",
         "2006-04-12", "Enugu", "12 Main Street", "Mr. Okafor", "08098765432"],
    ])


@staff_required
def import_credentials(request):
    """One-time download of the temporary passwords created by the last import."""
    creds = request.session.pop("import_credentials", None)
    if not creds:
        messages.error(request, "These login slips were already downloaded or have expired. "
                                "Use 'Reset password' on a student's page to issue a new one.")
        return redirect("student_list")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="student_login_slips.csv"'
    writer = csv.writer(response)
    writer.writerow(["Matric No", "Name", "Username", "Temporary password", "Login address"])
    login_url = request.build_absolute_uri(reverse("login"))
    for matric, name, pw in creds:
        writer.writerow([matric, name, matric, pw, login_url])
    return response


@staff_required
def course_import(request):
    department = Department.objects.first()
    form = CSVUploadForm(request.POST or None, request.FILES or None)
    errors = []
    if request.method == "POST" and form.is_valid():
        created, updated, errors = importers.import_courses(form.cleaned_data["file"], department)
        if not errors:
            messages.success(request, f"Courses imported: {created} new, {updated} updated.")
            return redirect("course_list")
    return render(request, "records/import.html", {
        "form": form, "errors": errors, "kind": "courses", "title": "Import courses",
        "template_url": reverse("course_import_template"), "columns": importers.COURSE_COLUMNS,
        "required": importers.COURSE_REQUIRED,
        "lecturers": User.objects.filter(role=User.Role.LECTURER, is_active=True),
    })


@staff_required
def course_import_template(request):
    return _csv_template("courses_template.csv", importers.COURSE_COLUMNS, [
        ["CSC 101", "Introduction to Computer Science", "3", "100", "FIRST", "", "no"],
        ["CSC 102", "Introduction to Programming", "3", "100", "SECOND", "", "no"],
    ])


# ---------------------------------------------------------------------------
# End-of-session promotion
# ---------------------------------------------------------------------------
@staff_required
def promote_students(request):
    session = AcademicSession.get_current()
    department = Department.objects.first()
    final = department.final_level if department else 400
    active = Student.objects.filter(status=Student.Status.ACTIVE)
    by_level = {row["level"]: row["n"] for row in active.values("level").annotate(n=Count("id"))}

    if request.method == "POST":
        action = request.POST.get("action")
        if session is None:
            messages.error(request, "Set a current session first.")
        elif action == "promote":
            if session.students_promoted:
                messages.error(request, f"Students were already promoted into {session}. Promotion can only run once per session.")
            else:
                moved = 0
                with transaction.atomic():
                    # Highest level first, so nobody is promoted twice.
                    for level in sorted((lv for lv in by_level if lv < final), reverse=True):
                        moved += active.filter(level=level).update(level=level + 100)
                    session.students_promoted = True
                    session.save()
                    AuditLog.objects.create(user=request.user, action=AuditLog.Action.UPDATE, model_name="Student",
                                            object_repr=f"Promoted {moved} students into {session}")
                messages.success(request, f"Promoted {moved} student(s) one level up for {session}.")
        elif action == "graduate":
            min_cgpa = Decimal(str(settings.DEGREE_CLASSES[-2][0]))  # lowest passing class
            candidates = [s for s in active.filter(level=final)]
            graduated, held = 0, []
            with transaction.atomic():
                for s in candidates:
                    if s.cgpa() >= min_cgpa and not Registration.objects.filter(student=s).exclude(
                            result__status=Result.Status.APPROVED).exists():
                        s.status = Student.Status.GRADUATED
                        s.save()
                        graduated += 1
                    else:
                        held.append(s.matric_no)
            messages.success(request, f"Marked {graduated} final-year student(s) as graduated.")
            if held:
                messages.warning(request, f"Not graduated (CGPA below {min_cgpa} or results still outstanding): "
                                          + ", ".join(held[:30]) + ("..." if len(held) > 30 else ""))
        return redirect("promote_students")

    return render(request, "records/promote.html", {
        "session": session, "by_level": sorted(by_level.items()), "final": final,
        "final_count": by_level.get(final, 0),
    })


# ---------------------------------------------------------------------------
# Protected files and backups
# ---------------------------------------------------------------------------
@login_required
def student_photo(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if not (_can_view_student(request.user, student) or request.user.is_lecturer):
        raise PermissionDenied
    if not student.photo:
        raise Http404
    return FileResponse(student.photo.open("rb"))


@admin_required
def backup_download(request):
    """Download a complete JSON backup of the database (restore with: manage.py loaddata <file>)."""
    out = io.StringIO()
    management.call_command(
        "dumpdata", "--natural-foreign", "--natural-primary", "--indent", "1",
        "--exclude", "contenttypes", "--exclude", "auth.permission", "--exclude", "sessions",
        "--exclude", "admin.logentry", stdout=out,
    )
    AuditLog.objects.create(user=request.user, action=AuditLog.Action.UPDATE, model_name="Backup",
                            object_repr="Downloaded full database backup")
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response = HttpResponse(out.getvalue(), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="sars-backup-{stamp}.json"'
    return response
