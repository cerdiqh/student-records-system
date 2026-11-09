from datetime import date
from decimal import Decimal

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


class BaseSetup(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("admin", password=PW, role=User.Role.ADMIN)
        cls.registrar = User.objects.create_user("reg", password=PW, role=User.Role.REGISTRAR)
        cls.lecturer = User.objects.create_user("lec", password=PW, role=User.Role.LECTURER, first_name="Ada", last_name="Obi")
        cls.other_lecturer = User.objects.create_user("lec2", password=PW, role=User.Role.LECTURER)
        cls.dept = Department.objects.create(name="Computer Science", code="CSC", faculty="Science")
        cls.session = AcademicSession.objects.create(
            name="2025/2026", start_date=date(2025, 10, 1), end_date=date(2026, 8, 31), is_current=True)
        cls.c1 = Course.objects.create(code="CSC 101", title="Intro", units=3, level=100, semester="FIRST",
                                       department=cls.dept, lecturer=cls.lecturer)
        cls.c2 = Course.objects.create(code="MTH 101", title="Maths", units=2, level=100, semester="FIRST",
                                       department=cls.dept, lecturer=cls.other_lecturer)
        su = User.objects.create_user("CSC/2025/001", password=PW, role=User.Role.STUDENT, first_name="Amina", last_name="Bello")
        cls.student = Student.objects.create(user=su, matric_no="CSC/2025/001", department=cls.dept, level=100,
                                             entry_session=cls.session, gender="F")
        su2 = User.objects.create_user("CSC/2025/002", password=PW, role=User.Role.STUDENT)
        cls.student2 = Student.objects.create(user=su2, matric_no="CSC/2025/002", department=cls.dept, level=100,
                                              entry_session=cls.session, gender="M")


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
        # (3*5 + 2*1) / 5 = 3.40
        self.assertEqual(calculate_gpa([r1, r2]), Decimal("3.40"))
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

    def test_registrar_cannot_open_audit_log(self):
        self.client.login(username="reg", password=PW)
        self.assertEqual(self.client.get(reverse("audit_log")).status_code, 403)
        self.client.login(username="admin", password=PW)
        self.assertEqual(self.client.get(reverse("audit_log")).status_code, 200)

    def test_all_dashboards_render(self):
        for username in ("admin", "reg", "lec", "CSC/2025/001"):
            self.client.login(username=username, password=PW)
            self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200, username)


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
        self.client.get(url)  # creates blank result rows
        result = Result.objects.get(registration=reg)
        resp = self.client.post(url, {
            "session": self.session.pk, "action": "submit",
            f"r{result.pk}-ca_score": "28", f"r{result.pk}-exam_score": "50",
        })
        self.assertEqual(resp.status_code, 302)
        result.refresh_from_db()
        self.assertEqual((result.total, result.grade, result.status), (Decimal("78"), "A", Result.Status.SUBMITTED))

        self.client.login(username="reg", password=PW)
        self.client.post(reverse("approve_results", args=[self.c1.pk]), {"session": self.session.pk, "action": "approve"})
        result.refresh_from_db()
        self.assertEqual(result.status, Result.Status.APPROVED)
        self.assertEqual(self.student.cgpa(), Decimal("5.00"))

        # Approved results are locked: a lecturer post must not change them.
        self.client.login(username="lec", password=PW)
        self.client.post(url, {"session": self.session.pk, "action": "save",
                               f"r{result.pk}-ca_score": "0", f"r{result.pk}-exam_score": "0"})
        result.refresh_from_db()
        self.assertEqual(result.total, Decimal("78"))

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

    def test_staff_creates_student_with_login(self):
        self.client.login(username="reg", password=PW)
        resp = self.client.post(reverse("student_create"), {
            "matric_no": "csc/2025/010", "first_name": "John", "last_name": "Doe", "password": "Another@Pass9",
            "department": self.dept.pk, "level": 100, "entry_session": self.session.pk, "gender": "M", "status": "ACTIVE",
        })
        self.assertEqual(resp.status_code, 302)
        s = Student.objects.get(matric_no="CSC/2025/010")
        self.assertTrue(self.client.login(username="CSC/2025/010", password="Another@Pass9"))
        self.assertEqual(s.user.role, User.Role.STUDENT)

    def test_transcript_pdf(self):
        reg = Registration.objects.create(student=self.student, course=self.c1, session=self.session)
        Result.objects.create(registration=reg, ca_score=20, exam_score=40, status=Result.Status.APPROVED)
        self.client.login(username="CSC/2025/001", password=PW)
        resp = self.client.get(reverse("transcript_pdf", args=[self.student.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(reverse("transcript", args=[self.student.pk])).status_code, 200)


class SetupTests(TestCase):
    def setUp(self):
        accounts.middleware._setup_done = False

    def tearDown(self):
        accounts.middleware._setup_done = False

    def test_fresh_install_redirects_to_setup_and_completes(self):
        self.assertRedirects(self.client.get("/"), reverse("setup"), fetch_redirect_response=False)
        resp = self.client.post(reverse("setup"), {
            "institution_name": "University of Jos", "faculty": "Natural Sciences",
            "department_name": "Computer Science", "department_code": "csc", "final_level": 400,
            "session_name": "2025/2026", "session_start": "2025-10-01", "session_end": "2026-08-31",
            "admin_first_name": "Ada", "admin_last_name": "Eze", "admin_username": "hod",
            "admin_password": "Very$ecure2026", "admin_password2": "Very$ecure2026",
        })
        self.assertRedirects(resp, reverse("dashboard"))
        self.assertEqual(Institution.load().name, "University of Jos")
        self.assertEqual(Department.objects.get().code, "CSC")
        self.assertTrue(AcademicSession.get_current())
        self.assertTrue(User.objects.get(username="hod").is_superuser)
        # Setup cannot be run a second time.
        self.assertRedirects(self.client.get(reverse("setup")), reverse("dashboard"))


class PasswordSecurityTests(BaseSetup):
    def setUp(self):
        cache.clear()

    def test_new_student_gets_temp_password_and_must_change_it(self):
        self.client.login(username="reg", password=PW)
        resp = self.client.post(reverse("student_create"), {
            "matric_no": "CSC/2025/050", "first_name": "Musa", "last_name": "Ali",
            "department": self.dept.pk, "level": 100, "entry_session": self.session.pk, "gender": "M", "status": "ACTIVE",
        }, follow=True)
        msg = [str(m) for m in resp.context["messages"] if "Temporary password" in str(m)][0]
        temp = msg.split(": ")[1].split(" ")[0]
        self.client.logout()
        self.assertTrue(self.client.login(username="CSC/2025/050", password=temp))
        # Any page sends them to change their password first.
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("password_change"))
        self.client.post(reverse("password_change"), {
            "old_password": temp, "new_password1": "MyOwn#Pass88", "new_password2": "MyOwn#Pass88"})
        self.assertFalse(User.objects.get(username="CSC/2025/050").must_change_password)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "lec", "password": "wrong"})
        resp = self.client.post(reverse("login"), {"username": "lec", "password": PW})
        self.assertContains(resp, "locked")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_registrar_can_reset_student_but_not_staff_password(self):
        self.client.login(username="reg", password=PW)
        self.client.post(reverse("reset_password", args=[self.student.user_id]))
        self.assertTrue(User.objects.get(pk=self.student.user_id).must_change_password)
        self.assertEqual(self.client.post(reverse("reset_password", args=[self.lecturer.pk])).status_code, 403)


class ImportTests(BaseSetup):
    def _upload(self, url_name, content):
        self.client.login(username="reg", password=PW)
        return self.client.post(reverse(url_name), {"file": SimpleUploadedFile("data.csv", content, content_type="text/csv")})

    def test_student_import_creates_accounts_and_login_slips(self):
        csv_bytes = (b"matric_no,surname,first_name,gender,level,entry_session,email\n"
                     b"CSC/2025/101,Okoro,Ngozi,F,100,2025/2026,ngozi@example.com\n"
                     b"CSC/2025/102,Bello,Sani,m,100,2025/2026,\n")
        resp = self._upload("student_import", csv_bytes)
        self.assertContains(resp, "2 student(s) imported")
        s = Student.objects.get(matric_no="CSC/2025/102")
        self.assertEqual((s.gender, s.user.role, s.user.must_change_password), ("M", User.Role.STUDENT, True))
        slips = self.client.get(reverse("import_credentials"))
        self.assertIn(b"CSC/2025/101", slips.content)
        # The slips can only be downloaded once.
        self.assertEqual(self.client.get(reverse("import_credentials")).status_code, 302)

    def test_student_import_is_all_or_nothing(self):
        csv_bytes = (b"matric_no,surname,first_name,gender,level,entry_session\n"
                     b"CSC/2025/201,Good,Row,M,100,2025/2026\n"
                     b"CSC/2025/001,Dup,Licate,F,100,2025/2026\n"
                     b"CSC/2025/203,Bad,Level,F,700,1999/2000\n")
        resp = self._upload("student_import", csv_bytes)
        self.assertContains(resp, "Nothing was imported")
        self.assertContains(resp, "already exists")
        self.assertContains(resp, "level must be")
        self.assertFalse(Student.objects.filter(matric_no="CSC/2025/201").exists())

    def test_course_import_creates_and_updates(self):
        csv_bytes = (b"code,title,units,level,semester,lecturer_username,elective\n"
                     b"csc 101,Intro to Computing,3,100,FIRST,,no\n"
                     b"CSC 102,Programming,3,100,2,lec,yes\n")
        resp = self._upload("course_import", csv_bytes)
        self.assertRedirects(resp, reverse("course_list"))
        self.c1.refresh_from_db()
        self.assertEqual((self.c1.title, self.c1.lecturer), ("Intro to Computing", self.lecturer))  # lecturer kept
        c = Course.objects.get(code="CSC 102")
        self.assertEqual((c.semester, c.lecturer, c.is_elective), ("SECOND", self.lecturer, True))


class PromotionAndResultTests(BaseSetup):
    def test_promotion_runs_once_and_skips_final_year(self):
        self.student2.level = 400
        self.student2.save()
        self.client.login(username="reg", password=PW)
        self.client.post(reverse("promote_students"), {"action": "promote"})
        self.client.post(reverse("promote_students"), {"action": "promote"})  # second click does nothing
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
        Registration.objects.create(student=self.student2, course=self.c1, session=self.session)  # no result
        self.client.login(username="reg", password=PW)
        self.client.post(reverse("promote_students"), {"action": "graduate"})
        self.student.refresh_from_db()
        self.student2.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.GRADUATED)
        self.assertEqual(self.student2.status, Student.Status.ACTIVE)

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

    def test_backup_download(self):
        self.client.login(username="admin", password=PW)
        resp = self.client.get(reverse("backup_download"))
        self.assertEqual(resp["Content-Type"], "application/json")
        self.assertIn(b"CSC/2025/001", resp.content)
