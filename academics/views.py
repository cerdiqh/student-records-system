from django.contrib import messages
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import lecturer_or_staff_required, staff_required

from .forms import AcademicSessionForm, CourseForm
from .models import AcademicSession, Course, Level, Semester


@lecturer_or_staff_required
def course_list(request):
    courses = Course.objects.select_related("lecturer", "department")
    if request.user.is_lecturer:
        courses = courses.filter(lecturer=request.user)
    q = request.GET.get("q", "").strip()
    if q:
        courses = courses.filter(Q(code__icontains=q) | Q(title__icontains=q))
    level = request.GET.get("level")
    if level:
        courses = courses.filter(level=level)
    semester = request.GET.get("semester")
    if semester:
        courses = courses.filter(semester=semester)
    session = AcademicSession.get_current()
    courses = courses.annotate(
        enrolled=Count("registrations", filter=Q(registrations__session=session))
    )
    return render(request, "academics/course_list.html", {
        "courses": courses, "q": q, "level": level, "semester": semester,
        "levels": Level.choices, "semesters": Semester.choices,
    })


@staff_required
def course_form(request, pk=None):
    course = get_object_or_404(Course, pk=pk) if pk else None
    form = CourseForm(request.POST or None, instance=course)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Course {saved.code} saved.")
        return redirect("course_list")
    return render(request, "form.html", {"form": form, "title": f"Edit {course.code}" if course else "New course", "back": "course_list"})


@staff_required
@require_POST
def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk)
    try:
        course.delete()
        messages.success(request, f"Course {course.code} deleted.")
    except ProtectedError:
        messages.error(
            request,
            f"{course.code} has student registrations and cannot be deleted. Mark it inactive instead.",
        )
    return redirect("course_list")


@staff_required
def session_list(request):
    sessions = AcademicSession.objects.annotate(n_reg=Count("registrations"))
    return render(request, "academics/session_list.html", {"sessions": sessions})


@staff_required
def session_form(request, pk=None):
    session = get_object_or_404(AcademicSession, pk=pk) if pk else None
    form = AcademicSessionForm(request.POST or None, instance=session)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Session {saved.name} saved.")
        return redirect("session_list")
    return render(request, "form.html", {"form": form, "title": f"Edit session {session}" if session else "New academic session", "back": "session_list"})
