"""Role-based access control for views."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Allow access only to users whose role is in `roles`. Superusers always pass."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user
            if user.is_superuser or user.role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("You do not have permission to view this page.")

        return wrapper

    return decorator


admin_required = role_required("ADMIN")
staff_required = admin_required  # the administrator manages all records
lecturer_or_staff_required = role_required("ADMIN", "LECTURER")
student_required = role_required("STUDENT")
