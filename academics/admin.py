from django.contrib import admin

from .models import AcademicSession, Course, Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "faculty", "head")


@admin.register(AcademicSession)
class AcademicSessionAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_current", "current_semester", "registration_open")
    list_editable = ("is_current", "current_semester", "registration_open")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "units", "level", "semester", "lecturer", "is_active")
    list_filter = ("level", "semester", "is_elective", "is_active")
    search_fields = ("code", "title")
