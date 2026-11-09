from .models import AcademicSession, Department, Institution


def current_session(request):
    institution = Institution.load()
    department = Department.objects.first()
    return {
        "current_session": AcademicSession.get_current(),
        "institution": institution,
        "department": department,
        "INSTITUTION_NAME": institution.name if institution else "Student Academic Records",
        "DEPARTMENT_NAME": f"Department of {department.name}" if department else "",
    }
