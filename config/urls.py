from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from academics import views as academics
from accounts import views as accounts
from records import views as records

admin.site.site_header = "Student Academic Records - Administration"
admin.site.site_title = "SARS Admin"

urlpatterns = [
    path("admin/", admin.site.urls),

    # Authentication
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/", auth_views.PasswordChangeView.as_view(
        template_name="form.html", success_url="/password/done/",
        extra_context={"title": "Change password", "back": "dashboard"}), name="password_change"),
    path("password/done/", auth_views.PasswordChangeDoneView.as_view(), name="password_change_done"),

    # Dashboard
    path("", records.dashboard, name="dashboard"),

    # Students
    path("students/", records.student_list, name="student_list"),
    path("students/new/", records.student_form, name="student_create"),
    path("students/export/", records.export_students, name="student_export"),
    path("students/<int:pk>/", records.student_detail, name="student_detail"),
    path("students/<int:pk>/edit/", records.student_form, name="student_edit"),
    path("students/<int:pk>/delete/", records.student_delete, name="student_delete"),
    path("students/<int:pk>/register/", records.register_courses, name="student_register_courses"),
    path("students/<int:pk>/transcript/", records.transcript, name="transcript"),
    path("students/<int:pk>/transcript.pdf", records.transcript_pdf, name="transcript_pdf"),
    path("my-record/", records.my_record, name="my_record"),
    path("register-courses/", records.register_courses, name="register_courses"),

    # Courses and sessions
    path("courses/", academics.course_list, name="course_list"),
    path("courses/new/", academics.course_form, name="course_create"),
    path("courses/<int:pk>/edit/", academics.course_form, name="course_edit"),
    path("courses/<int:pk>/delete/", academics.course_delete, name="course_delete"),
    path("sessions/", academics.session_list, name="session_list"),
    path("sessions/new/", academics.session_form, name="session_create"),
    path("sessions/<int:pk>/edit/", academics.session_form, name="session_edit"),

    # Results
    path("results/course/<int:pk>/", records.course_results, name="course_results"),
    path("results/course/<int:pk>/upload/", records.course_results_upload, name="course_results_upload"),
    path("results/course/<int:pk>/csv/", records.course_results_csv, name="course_results_csv"),
    path("results/approvals/", records.approval_list, name="approval_list"),
    path("results/course/<int:pk>/approve/", records.approve_results, name="approve_results"),

    # Administration
    path("staff/", accounts.staff_list, name="staff_list"),
    path("staff/new/", accounts.staff_form, name="staff_create"),
    path("staff/<int:pk>/edit/", accounts.staff_form, name="staff_edit"),
    path("audit-log/", records.audit_log, name="audit_log"),
]
