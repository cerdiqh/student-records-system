from .models import AcademicSession, Department, Institution


def current_session(request):
    institution = Institution.load()
    department = Department.objects.first()
    pending_lecturers = 0
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_admin_role:
        from accounts.models import User

        pending_lecturers = User.objects.filter(role=User.Role.LECTURER, is_approved=False, is_active=True).count()
    return {
        "pending_lecturers": pending_lecturers,
        "current_session": AcademicSession.get_current(),
        "institution": institution,
        "department": department,
        "INSTITUTION_NAME": institution.name if institution else "Student Academic Records",
        "DEPARTMENT_NAME": f"Department of {department.name}" if department else "",
    }
