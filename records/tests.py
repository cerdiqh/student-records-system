import re
from datetime import date
from decimal import Decimal

from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

import accounts.middleware
from academics.models import AcademicSession, Course, Department, Institution
from accounts.models import User

from .grading import compute_grade
from .models import AuditLog, Registration, Result, Student, calculate_gpa

PW = "Strong@Pass123"


def make_user(username, role, **extra):
    extra.setdefault("email", f"{username.replace('/', '.').lower()}@example.com")
    return User.objects.create_user(username, password=PW, role=role, email_verified=True, **extra)


def code_from_last_email():
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


class BaseSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("admin", User.Role.ADMIN)
        cls.lecturer = make_user("lec", User.Role.LECTURER, first_name="Ada", last_name="Obi")
        cls.other_lecturer = make_user("lec2", User.Role.LECTURER)
        cls.dept = Department.objects.create(name="Computer Science", code="CSC", faculty="Science")
        cls.session = AcademicSession.objects.create(
            name="2025/2026", start_date=date(2025, 10, 1), end_date=date(2026, 8, 31), is_current=True)
        cls.c1 = Course.objects.create(code="CSC 101", title="Intro", units=3, level=100, semester="FIRST",
                                       department=cls.dept, lecturer=cls.lecturer)
        cls.c2 = Course.objects.create(code="MTH 101", title="Maths", units=2, level=100, semester="FIRST",
                                       department=cls.dept, lecturer=cls.other_lecturer)
        su = make_user("CSC/2025/001", User.Role.STUDENT, first_name="Amina", last_name="Bello")
        cls.student = Student.objects.create(user=su, matric_no="CSC/2025/001", department=cls.dept, level=100,
                                             entry_session=cls.session, gender="F")
        su2 = make_user("CSC/2025/002", User.Role.STUDENT)
        cls.student2 = Student.objects.create(user=su2, matric_no="CSC/2025/002", department=cls.dept, level=100,
                                              entry_session=cls.session, gender="M")

    def setUp(self):
        cache.clear()


# ---------------------------------------------------------------------------
# Grading and records
# ---------------------------------------------------------------------------
class GradingTests(TestCase):
    def test_grade_boundaries(self):
        self.assertEqual(compute_grade(70), ("A", 5))
        self.assertEqual(compute_grade(69.99), ("B", 4))
        self.assertEqual(compute_grade(50), ("C", 3))
        self.assertEqual(compute_grade(45), ("D", 2))
        self.assertEqual(compute_grade(40), ("E", 1))
        self.assertEqual(compute_grade(39), ("F", 0))
        self.assertEqual(compute_grade(0), ("F", 0))


class ResultModelTests(BaseSetup):
    def test_total_and_grade_computed_on_save(self):
        reg = Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        r = Result.objects.create(registration=reg, ca_score=25, exam_score=48)
        self.assertEqual(r.total, Decimal("73"))
        self.assertEqual((r.grade, r.grade_point), ("A", 5))

    def test_gpa_is_unit_weighted(self):
        r1 = Result.objects.create(registration=Registration.objects.create(student=self.student, course=self.c1, session=self.session),
                                   ca_score=30, exam_score=45, status=Result.Status.APPROVED)  # A, 3 units
        r2 = Result.objects.create(registration=Registration.objects.create(student=self.student, course=self.c2, session=self.session),
                                   ca_score=20, exam_score=20, status=Result.Status.APPROVED)  # E, 2 units
        self.assertEqual(calculate_gpa([r1, r2]), Decimal("3.40"))  # (3*5 + 2*1) / 5
        self.assertEqual(self.student.cgpa(), Decimal("3.40"))
        self.assertEqual(self.student.degree_class(), "Second Class Honours (Lower Division)")

    def test_unapproved_results_do_not_count(self):
        reg = Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        Result.objects.create(registration=reg, ca_score=30, exam_score=60, status=Result.Status.SUBMITTED)
        self.assertEqual(self.student.cgpa(), Decimal("0.00"))

    def test_duplicate_registration_rejected(self):
        from django.db import IntegrityError
        Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        with self.assertRaises(IntegrityError):
            Registration.objects.create(student=self.student, course=self.c1, session=self.session)

    def test_changes_are_audited(self):
        reg = Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        r = Result.objects.create(registration=reg, ca_score=10, exam_score=10)
        r.exam_score = 50
        r.save()
        log = AuditLog.objects.filter(model_name="Result", action=AuditLog.Action.UPDATE).first()
        self.assertIsNotNone(log)
        self.assertIn("exam_score", log.changes)


# ---------------------------------------------------------------------------
# Sign up, email verification and approval
# ---------------------------------------------------------------------------
class AdminSignupTests(TestCase):
    def setUp(self):
        accounts.middleware._setup_done = False

    def tearDown(self):
        accounts.middleware._setup_done = False

    def test_first_visitor_signs_up_as_admin_and_verifies_email(self):
        self.assertRedirects(self.client.get("/"), reverse("setup"), fetch_redirect_response=False)
        resp = self.client.post(reverse("setup"), {
            "institution_name": "University of Jos", "faculty": "Natural Sciences",
            "department_name": "Computer Science", "department_code": "csc", "final_level": 400,
            "session_name": "2025/2026", "session_start": "2025-10-01", "session_end": "2026-08-31",
            "admin_first_name": "Ada", "admin_last_name": "Eze", "admin_email": "HOD@unijos.edu.ng",
            "password1": "Very$ecure2026", "password2": "Very$ecure2026",
        })
        self.assertRedirects(resp, reverse("verify_email"))
        admin = User.objects.get(email="hod@unijos.edu.ng")
        self.assertTrue(admin.is_superuser)
        self.assertFalse(admin.email_verified)
        # Cannot reach the dashboard before confirming the email.
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("verify_email"))
        self.client.post(reverse("verify_email"), {"code": code_from_last_email()})
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(Institution.load().name, "University of Jos")
        # Admin sign-up is closed now.
        self.client.logout()
        self.assertRedirects(self.client.get(reverse("setup")), reverse("signup"), fetch_redirect_response=False)
        # And they can sign in with their email.
        self.assertTrue(self.client.login(username="hod@unijos.edu.ng", password="Very$ecure2026"))


class SignupTests(BaseSetup):
    STUDENT = {
        "surname": "Okoro", "first_name": "Ngozi", "other_names": "", "email": "ngozi@gmail.com", "phone": "",
        "matric_no": "csc/2025/077", "level": 100, "gender": "F", "date_of_birth": "",
        "password1": "Ngozi#2025pass", "password2": "Ngozi#2025pass",
    }

    def test_student_signs_up_verifies_and_reaches_dashboard(self):
        data = dict(self.STUDENT, entry_session=self.session.pk)
        resp = self.client.post(reverse("signup_student"), data)
        self.assertRedirects(resp, reverse("verify_email"))
        student = Student.objects.get(matric_no="CSC/2025/077")
        self.assertEqual((student.user.email, student.user.role), ("ngozi@gmail.com", User.Role.STUDENT))
        self.assertIn("ngozi@gmail.com", mail.outbox[-1].to)
        # Wrong code is refused.
        self.client.post(reverse("verify_email"), {"code": "000000" if code_from_last_email() != "000000" else "111111"})
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("verify_email"))
        # Right code opens the dashboard straight away (students need no approval).
        self.client.post(reverse("verify_email"), {"code": code_from_last_email()})
        resp = self.client.get(reverse("dashboard"))
        self.assertContains(resp, "Welcome, Ngozi")
        # Can sign in later with email or matric number.
        self.client.logout()
        self.assertTrue(self.client.login(username="ngozi@gmail.com", password="Ngozi#2025pass"))
        self.client.logout()
        self.assertTrue(self.client.login(username="CSC/2025/077", password="Ngozi#2025pass"))

    def test_duplicate_email_or_matric_rejected(self):
        data = dict(self.STUDENT, entry_session=self.session.pk, email="CSC.2025.001@example.com")
        self.assertContains(self.client.post(reverse("signup_student"), data), "already exists")
        data = dict(self.STUDENT, entry_session=self.session.pk, matric_no="CSC/2025/001")
        self.assertContains(self.client.post(reverse("signup_student"), data), "already exists")
        self.assertFalse(User.objects.filter(email="ngozi@gmail.com").exists())

    def test_lecturer_must_be_approved_by_admin(self):
        resp = self.client.post(reverse("signup_lecturer"), {
            "title": "Dr.", "surname": "Musa", "first_name": "Ibrahim", "email": "imusa@unijos.edu.ng",
            "phone": "", "staff_id": "SP1234", "password1": "Lect#Pass2025", "password2": "Lect#Pass2025",
        })
        self.assertRedirects(resp, reverse("verify_email"))
        self.client.post(reverse("verify_email"), {"code": code_from_last_email()})
        # Verified but not approved: stuck on the waiting page; admin was emailed.
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("pending_approval"))
        self.assertIn("admin@example.com", mail.outbox[-1].to)
        self.assertEqual(self.client.get(reverse("course_list")).status_code, 302)

        lecturer = User.objects.get(email="imusa@unijos.edu.ng")
        admin_client = self.client_class()
        admin_client.login(username="admin", password=PW)
        self.assertContains(admin_client.get(reverse("user_approvals")), "imusa@unijos.edu.ng")
        admin_client.post(reverse("approve_user", args=[lecturer.pk]), {"action": "approve"})
        self.assertIn("imusa@unijos.edu.ng", mail.outbox[-1].to)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_rejected_lecturer_is_disabled(self):
        pending = User.objects.create_user("x@y.com", email="x@y.com", password=PW, role=User.Role.LECTURER,
                                           email_verified=True, is_approved=False)
        self.client.login(username="admin", password=PW)
        self.client.post(reverse("approve_user", args=[pending.pk]), {"action": "reject"})
        pending.refresh_from_db()
        self.assertFalse(pending.is_active)
        self.assertFalse(self.client_class().login(username="x@y.com", password=PW))

    def test_verification_code_attempt_limit(self):
        user = User.objects.create_user("t@t.com", email="t@t.com", password=PW, role=User.Role.STUDENT)
        self.client.login(username="t@t.com", password=PW)
        self.client.post(reverse("verify_email"), {"action": "resend"})
        code = code_from_last_email()
        wrong = "123456" if code != "123456" else "654321"
        for _ in range(5):
            self.client.post(reverse("verify_email"), {"code": wrong})
        self.client.post(reverse("verify_email"), {"code": code})  # right code, but too late
        user.refresh_from_db()
        self.assertFalse(user.email_verified)


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------
class AccessControlTests(BaseSetup):
    def test_login_required(self):
        resp = self.client.get(reverse("student_list"))
        self.assertRedirects(resp, f"{reverse('login')}?next={reverse('student_list')}")

    def test_student_cannot_see_other_student(self):
        self.client.login(username="CSC/2025/001", password=PW)
        self.assertEqual(self.client.get(reverse("student_detail", args=[self.student.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("student_detail", args=[self.student2.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("student_list")).status_code, 403)

    def test_lecturer_limited_to_own_courses(self):
        self.client.login(username="lec", password=PW)
        self.assertEqual(self.client.get(reverse("course_results", args=[self.c1.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("course_results", args=[self.c2.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("user_approvals")).status_code, 403)

    def test_only_admin_opens_audit_log(self):
        self.client.login(username="lec", password=PW)
        self.assertEqual(self.client.get(reverse("audit_log")).status_code, 403)
        self.client.login(username="admin", password=PW)
        self.assertEqual(self.client.get(reverse("audit_log")).status_code, 200)

    def test_all_dashboards_render(self):
        for username in ("admin", "lec", "CSC/2025/001"):
            self.client.login(username=username, password=PW)
            self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200, username)


class PasswordSecurityTests(BaseSetup):
    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "lec@example.com", "password": "wrong"})
        resp = self.client.post(reverse("login"), {"username": "lec@example.com", "password": PW})
        self.assertContains(resp, "locked")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_admin_reset_forces_new_password(self):
        self.client.login(username="admin", password=PW)
        resp = self.client.post(reverse("reset_password", args=[self.student.user_id]), follow=True)
        temp = [str(m) for m in resp.context["messages"] if "Temporary password" in str(m) or "temporary password" in str(m)][0]
        temp = temp.split(": ")[1].split(" ")[0]
        c = self.client_class()
        self.assertTrue(c.login(username="CSC/2025/001", password=temp))
        self.assertRedirects(c.get(reverse("dashboard")), reverse("password_change"))
        c.post(reverse("password_change"), {"old_password": temp, "new_password1": "MyOwn#Pass88", "new_password2": "MyOwn#Pass88"})
        self.assertEqual(c.get(reverse("dashboard")).status_code, 200)

    def test_lecturer_cannot_reset_passwords(self):
        self.client.login(username="lec", password=PW)
        self.assertEqual(self.client.post(reverse("reset_password", args=[self.student.user_id])).status_code, 403)


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------
class WorkflowTests(BaseSetup):
    def test_student_registers_courses_within_unit_limit(self):
        self.client.login(username="CSC/2025/001", password=PW)
        resp = self.client.post(reverse("register_courses"), {"courses": [self.c1.pk, self.c2.pk]})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Registration.objects.filter(student=self.student).count(), 2)

    def test_closed_registration_blocks_students(self):
        self.session.registration_open = False
        self.session.save()
        self.client.login(username="CSC/2025/001", password=PW)
        self.client.post(reverse("register_courses"), {"courses": [self.c1.pk]})
        self.assertFalse(Registration.objects.filter(student=self.student).exists())

    def test_enter_submit_approve_flow(self):
        reg = Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        self.client.login(username="lec", password=PW)
        url = reverse("course_results", args=[self.c1.pk])
        self.client.get(url)
        result = Result.objects.get(registration=reg)
        resp = self.client.post(url, {
            "session": self.session.pk, "action": "submit",
            f"r{result.pk}-ca_score": "28", f"r{result.pk}-exam_score": "50",
        })
        self.assertEqual(resp.status_code, 302)
        result.refresh_from_db()
        self.assertEqual((result.total, result.grade, result.status), (Decimal("78"), "A", Result.Status.SUBMITTED))

        self.client.login(username="admin", password=PW)
        self.client.post(reverse("approve_results", args=[self.c1.pk]), {"session": self.session.pk, "action": "approve"})
        result.refresh_from_db()
        self.assertEqual(result.status, Result.Status.APPROVED)
        self.assertEqual(self.student.cgpa(), Decimal("5.00"))

        self.client.login(username="lec", password=PW)
        self.client.post(url, {"session": self.session.pk, "action": "save",
                               f"r{result.pk}-ca_score": "0", f"r{result.pk}-exam_score": "0"})
        result.refresh_from_db()
        self.assertEqual(result.total, Decimal("78"))  # approved results are locked

    def test_invalid_score_rejected(self):
        Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        self.client.login(username="lec", password=PW)
        url = reverse("course_results", args=[self.c1.pk])
        self.client.get(url)
        result = Result.objects.get()
        self.client.post(url, {"session": self.session.pk, "action": "save",
                               f"r{result.pk}-ca_score": "45", f"r{result.pk}-exam_score": "50"})
        result.refresh_from_db()
        self.assertIsNone(result.total)

    def test_blank_scores_are_not_submitted(self):
        Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        Registration.objects.create(student=self.student2, course=self.c1, session=self.session)
        self.client.login(username="lec", password=PW)
        url = reverse("course_results", args=[self.c1.pk])
        self.client.get(url)
        r1, r2 = Result.objects.order_by("registration__student__matric_no")
        self.client.post(url, {"session": self.session.pk, "action": "submit",
                               f"r{r1.pk}-ca_score": "25", f"r{r1.pk}-exam_score": "50",
                               f"r{r2.pk}-ca_score": "", f"r{r2.pk}-exam_score": ""})
        r1.refresh_from_db()
        r2.refresh_from_db()
        self.assertEqual(r1.status, Result.Status.SUBMITTED)
        self.assertEqual((r2.status, r2.total, r2.grade), (Result.Status.DRAFT, None, ""))

    def test_csv_upload(self):
        Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        self.client.login(username="lec", password=PW)
        self.client.get(reverse("course_results", args=[self.c1.pk]))
        csv_bytes = b"matric_no,ca_score,exam_score\ncsc/2025/001,20,41\nCSC/9999/999,10,10\n"
        resp = self.client.post(reverse("course_results_upload", args=[self.c1.pk]), {
            "session": self.session.pk, "file": SimpleUploadedFile("scores.csv", csv_bytes, content_type="text/csv")})
        self.assertEqual(resp.status_code, 302)
        result = Result.objects.get()
        self.assertEqual((result.total, result.grade), (Decimal("61"), "B"))

    def test_transcript_pdf(self):
        reg = Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        Result.objects.create(registration=reg, ca_score=20, exam_score=40, status=Result.Status.APPROVED)
        self.client.login(username="CSC/2025/001", password=PW)
        resp = self.client.get(reverse("transcript_pdf", args=[self.student.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(reverse("transcript", args=[self.student.pk])).status_code, 200)

    def test_promotion_runs_once_and_skips_final_year(self):
        self.student2.level = 400
        self.student2.save()
        self.client.login(username="admin", password=PW)
        self.client.post(reverse("promote_students"), {"action": "promote"})
        self.client.post(reverse("promote_students"), {"action": "promote"})
        self.student.refresh_from_db()
        self.student2.refresh_from_db()
        self.assertEqual((self.student.level, self.student2.level), (200, 400))

    def test_graduation_requires_complete_approved_results(self):
        self.student.level = 400
        self.student.save()
        reg = Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        Result.objects.create(registration=reg, ca_score=20, exam_score=40, status=Result.Status.APPROVED)
        self.student2.level = 400
        self.student2.save()
        Registration.objects.create(student=self.student2, course=self.c1, session=self.session)
        self.client.login(username="admin", password=PW)
        self.client.post(reverse("promote_students"), {"action": "graduate"})
        self.student.refresh_from_db()
        self.student2.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.GRADUATED)
        self.assertEqual(self.student2.status, Student.Status.ACTIVE)

    def test_course_import_creates_and_updates(self):
        csv_bytes = (b"code,title,units,level,semester,lecturer_username,elective\n"
                     b"csc 101,Intro to Computing,3,100,FIRST,,no\n"
                     b"CSC 102,Programming,3,100,2,lec,yes\n")
        self.client.login(username="admin", password=PW)
        resp = self.client.post(reverse("course_import"), {"file": SimpleUploadedFile("c.csv", csv_bytes, content_type="text/csv")})
        self.assertRedirects(resp, reverse("course_list"))
        self.c1.refresh_from_db()
        self.assertEqual((self.c1.title, self.c1.lecturer), ("Intro to Computing", self.lecturer))
        c = Course.objects.get(code="CSC 102")
        self.assertEqual((c.semester, c.lecturer, c.is_elective), ("SECOND", self.lecturer, True))

    def test_backup_download(self):
        self.client.login(username="admin", password=PW)
        resp = self.client.get(reverse("backup_download"))
        self.assertEqual(resp["Content-Type"], "application/json")
        self.assertIn(b"CSC/2025/001", resp.content)
