from django.contrib import admin

from .models import AuditLog, Registration, Result, Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("matric_no", "full_name", "level", "gender", "status")
    list_filter = ("level", "status", "gender")
    search_fields = ("matric_no", "user__first_name", "user__last_name")


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "session", "registered_at")
    list_filter = ("session", "course__semester", "course__level")
    search_fields = ("student__matric_no", "course__code")


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("registration", "ca_score", "exam_score", "total", "grade", "status")
    list_filter = ("status", "grade", "registration__session")
    search_fields = ("registration__student__matric_no", "registration__course__code")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "model_name", "object_repr")
    list_filter = ("action", "model_name")
    search_fields = ("object_repr", "changes")

    # The audit trail is read-only, even for superusers.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
