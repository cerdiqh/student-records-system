"""
Populate the database with realistic demo data for presentation and testing.

    python manage.py seed_demo

Creates: 1 department, 4 academic sessions, 32 courses (100-400 level),
an admin, 4 lecturers and 40 students with full result
histories (past sessions approved; current session partly entered).
"""
import random
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicSession, Course, Department, Institution, Semester
from accounts.models import User
from records.models import Registration, Result, Student

DEMO_PASSWORD = "Pass@1234"

COURSES = {
    100: [("CSC 101", "Introduction to Computer Science", 3, "FIRST"), ("MTH 101", "Elementary Mathematics I", 3, "FIRST"),
          ("PHY 101", "General Physics I", 3, "FIRST"), ("GST 111", "Communication in English", 2, "FIRST"),
          ("CSC 102", "Introduction to Programming", 3, "SECOND"), ("MTH 102", "Elementary Mathematics II", 3, "SECOND"),
          ("PHY 102", "General Physics II", 3, "SECOND"), ("GST 112", "Nigerian Peoples and Culture", 2, "SECOND")],
    200: [("CSC 201", "Computer Programming I", 3, "FIRST"), ("CSC 203", "Discrete Structures", 3, "FIRST"),
          ("MTH 201", "Mathematical Methods I", 3, "FIRST"), ("CSC 205", "Digital Logic Design", 2, "FIRST"),
          ("CSC 202", "Computer Programming II", 3, "SECOND"), ("CSC 204", "Data Structures", 3, "SECOND"),
          ("CSC 206", "Operating Systems I", 3, "SECOND"), ("STA 202", "Statistics for Computing", 2, "SECOND")],
    300: [("CSC 301", "Database Management Systems", 3, "FIRST"), ("CSC 303", "Software Engineering", 3, "FIRST"),
          ("CSC 305", "Computer Architecture", 3, "FIRST"), ("CSC 307", "Web Technologies", 2, "FIRST"),
          ("CSC 302", "Analysis of Algorithms", 3, "SECOND"), ("CSC 304", "Computer Networks", 3, "SECOND"),
          ("CSC 306", "Compiler Construction", 3, "SECOND"), ("CSC 399", "SIWES / Industrial Training", 6, "SECOND")],
    400: [("CSC 401", "Artificial Intelligence", 3, "FIRST"), ("CSC 403", "Computer Security", 3, "FIRST"),
          ("CSC 405", "Distributed Systems", 3, "FIRST"), ("CSC 407", "Human Computer Interaction", 2, "FIRST"),
          ("CSC 402", "Project Management", 2, "SECOND"), ("CSC 404", "Machine Learning", 3, "SECOND"),
          ("CSC 406", "Cloud Computing", 3, "SECOND"), ("CSC 499", "Final Year Project", 6, "SECOND")],
}

FIRST_NAMES_M = ["Chinedu", "Emeka", "Tunde", "Ibrahim", "Musa", "Samuel", "Daniel", "Yusuf", "Kelechi", "Ahmed", "Segun", "David"]
FIRST_NAMES_F = ["Amina", "Ngozi", "Funke", "Blessing", "Aisha", "Chioma", "Grace", "Zainab", "Ifeoma", "Esther", "Halima", "Mary"]
SURNAMES = ["Okafor", "Adeyemi", "Bello", "Eze", "Abubakar", "Okoro", "Balogun", "Usman", "Nwosu", "Lawal", "Obi", "Danjuma",
            "Ogunleye", "Ibe", "Suleiman", "Akande", "Nnamdi", "Yakubu", "Olawale", "Chukwu"]
STATES = ["Lagos", "Kano", "Enugu", "Oyo", "Kaduna", "Anambra", "Rivers", "Plateau", "Kwara", "Delta"]


class Command(BaseCommand):
    help = "Load demo data (department, sessions, courses, staff, students, results)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Run even if data already exists.")

    @transaction.atomic
    def handle(self, *args, force=False, **options):
        from django.conf import settings

        if not settings.DEBUG:
            self.stdout.write(self.style.ERROR("seed_demo is for testing only and is disabled when DEBUG=False."))
            return
        if Department.objects.exists() and not force:
            self.stdout.write(self.style.WARNING("Data already exists. Use --force to add demo data anyway."))
            return
        rng = random.Random(42)

        def make_user(username, first, last, role, title="", email=None, **extra):
            user, _ = User.objects.get_or_create(username=username, defaults=dict(
                first_name=first, last_name=last, role=role, title=title, email_verified=True,
                email=email or f"{username.lower().replace('/', '.')}@example.edu", **extra))
            user.set_password(DEMO_PASSWORD if username != "admin" else "Admin@1234")
            user.save()
            return user

        make_user("admin", "System", "Administrator", User.Role.ADMIN, is_staff=True, is_superuser=True)
        lecturers = [
            make_user("lecturer1", "Ibrahim", "Musa", User.Role.LECTURER, "Dr."),
            make_user("lecturer2", "Ngozi", "Okeke", User.Role.LECTURER, "Prof."),
            make_user("lecturer3", "Tunde", "Bakare", User.Role.LECTURER, "Dr."),
            make_user("lecturer4", "Aisha", "Garba", User.Role.LECTURER, "Mrs."),
        ]

        if not Institution.load():
            Institution(name="Demo University", registrar_name="Mrs. Grace Adebayo").save()
        dept, _ = Department.objects.get_or_create(
            code="CSC", defaults=dict(name="Computer Science", faculty="Faculty of Physical Sciences", head=lecturers[1]))

        sessions = []
        for i, year in enumerate(range(2022, 2026)):
            s, _ = AcademicSession.objects.get_or_create(name=f"{year}/{year + 1}", defaults=dict(
                start_date=date(year, 10, 1), end_date=date(year + 1, 8, 31)))
            sessions.append(s)
        current = sessions[-1]
        current.is_current = True
        current.current_semester = Semester.FIRST
        current.registration_open = True
        current.save()

        courses = {}
        for level, items in COURSES.items():
            for j, (code, title, units, sem) in enumerate(items):
                c, _ = Course.objects.get_or_create(code=code, defaults=dict(
                    title=title, units=units, level=level, semester=sem, department=dept,
                    lecturer=lecturers[(j + level // 100) % len(lecturers)]))
                courses.setdefault(level, []).append(c)

        # Students: 10 per level. Level L entered (4 - L/100) sessions before current.
        n = 0
        for level in (100, 200, 300, 400):
            entry_idx = len(sessions) - level // 100
            entry = sessions[entry_idx]
            for k in range(10):
                n += 1
                gender = "M" if k % 2 == 0 else "F"
                first = rng.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
                last = rng.choice(SURNAMES)
                matric = f"CSC/{entry.name[:4]}/{k + 1:03d}"
                user = make_user(matric, first, last, User.Role.STUDENT, email=f"{first.lower()}.{last.lower()}{n}@student.example.edu")
                ability = rng.uniform(42, 78)  # each student has a typical performance level
                student, _ = Student.objects.get_or_create(user=user, defaults=dict(
                    matric_no=matric, department=dept, level=level, entry_session=entry, gender=gender,
                    date_of_birth=date(2006 - level // 100 - rng.randint(0, 2), rng.randint(1, 12), rng.randint(1, 28)),
                    state_of_origin=rng.choice(STATES), address=f"{rng.randint(1, 99)} University Road",
                    guardian_name=f"Mr. {last}", guardian_phone=f"080{rng.randint(10000000, 99999999)}"))

                # Past sessions: register both semesters and approve results.
                for offset, sess in enumerate(sessions[entry_idx:]):
                    lvl = (offset + 1) * 100
                    is_current = sess == current
                    for c in courses[lvl]:
                        if is_current and c.semester == Semester.SECOND:
                            continue  # second semester not yet registered
                        reg, _ = Registration.objects.get_or_create(student=student, course=c, session=sess)
                        if is_current and rng.random() < 0.5:
                            continue  # some current results not yet entered
                        score = max(15, min(98, rng.gauss(ability, 9)))
                        ca = round(min(30, score * 0.3), 1)
                        exam = round(min(70, score - ca), 1)
                        result, _ = Result.objects.get_or_create(registration=reg, defaults=dict(
                            ca_score=ca, exam_score=exam, entered_by=c.lecturer))
                        if is_current:
                            result.status = Result.Status.SUBMITTED if c.level == 400 else Result.Status.DRAFT
                        else:
                            result.status = Result.Status.APPROVED
                            result.approved_at = timezone.now()
                        result.save()

        self.stdout.write(self.style.SUCCESS(
            f"Demo data loaded: {Student.objects.count()} students, {Course.objects.count()} courses, "
            f"{Result.objects.count()} results.\n"
            f"  Admin:           admin / Admin@1234\n"
            f"  Lecturer:        lecturer1 / {DEMO_PASSWORD}\n"
            f"  Student:         CSC/2024/001 / {DEMO_PASSWORD}"))
