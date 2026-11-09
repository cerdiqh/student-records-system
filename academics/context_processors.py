from django.conf import settings

from .models import AcademicSession


def current_session(request):
    return {
        "current_session": AcademicSession.get_current(),
        "INSTITUTION_NAME": settings.INSTITUTION_NAME,
        "DEPARTMENT_NAME": settings.DEPARTMENT_NAME,
    }
