from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from academics.models import AcademicSession, Course, Department, Level, Semester

from .grading import compute_grade


def validate_photo(file):
    if file.size > 1024 * 1024:
        raise ValidationError("Image is too large (max 1 MB).")
    if not file.name.lower().endswith((".jpg", ".jpeg", ".png")):
        raise ValidationError("Upload a JPG or PNG image.")


class Student(models.Model):
    class Gender(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"
        GRADUATED = "GRADUATED", "Graduated"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile"
    )
    matric_no = models.CharField("Matric number", max_length=20, unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="students")
    level = models.IntegerField(choices=Level.choices, default=Level.L100)
    entry_session = models.ForeignKey(
        AcademicSession, on_delete=models.PROTECT, related_name="entrants"
    )
    gender = models.CharField(max_length=1, choices=Gender.choices)
    photo = models.ImageField(
        "Passport photo", upload_to="photos/", blank=True,
        validators=[validate_photo], help_text="JPG or PNG, max 1 MB.",
    )
    date_of_birth = models.DateField(null=True, blank=True)
    state_of_origin = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    guardian_name = models.CharField(max_length=150, blank=True)
    guardian_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["matric_no"]

    def __str__(self):
        return f"{self.matric_no} - {self.full_name}"

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    # ----- Academic performance -----
    def approved_results(self):
        return Result.objects.filter(
            registration__student=self, status=Result.Status.APPROVED
        ).select_related("registration__course", "registration__session")

    def cgpa(self):
        return calculate_gpa(self.approved_results())

    def total_units_passed(self):
        return sum(
            r.registration.course.units for r in self.approved_results() if r.grade_point > 0
        )

    def degree_class(self):
        cgpa = self.cgpa()
        for minimum, label in settings.DEGREE_CLASSES:
            if cgpa >= Decimal(str(minimum)):
                return label
        return settings.DEGREE_CLASSES[-1][1]

    def semester_breakdown(self):
        """
        Group approved results by (session, semester), with GPA per semester and
        cumulative GPA up to that point. Used by the student record page and transcript.
        """
        results = list(
            self.approved_results().order_by(
                "registration__session__start_date",
                "registration__course__semester",
                "registration__course__code",
            )
        )
        groups = []
        index = {}
        for r in results:
            key = (r.registration.session_id, r.registration.course.semester)
            if key not in index:
                index[key] = len(groups)
                groups.append(
                    {
                        "session": r.registration.session,
                        "semester": r.registration.course.get_semester_display(),
                        "results": [],
                    }
                )
            groups[index[key]]["results"].append(r)

        cumulative = []
        for g in groups:
            cumulative.extend(g["results"])
            g["units"] = sum(r.registration.course.units for r in g["results"])
            g["points"] = sum(r.registration.course.units * r.grade_point for r in g["results"])
            g["gpa"] = calculate_gpa(g["results"])
            g["cgpa"] = calculate_gpa(cumulative)
        return groups


def calculate_gpa(results):
    """GPA = sum(units x grade point) / sum(units), rounded to 2 decimal places."""
    total_units = 0
    total_points = 0
    for r in results:
        units = r.registration.course.units
        total_units += units
        total_points += units * r.grade_point
    if total_units == 0:
        return Decimal("0.00")
    return (Decimal(total_points) / Decimal(total_units)).quantize(Decimal("0.01"))


class Registration(models.Model):
    """A student taking a course in a given session (course registration)."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="registrations")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="registrations")
    session = models.ForeignKey(
        AcademicSession, on_delete=models.PROTECT, related_name="registrations"
    )
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["session", "course__semester", "course__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course", "session"], name="unique_registration"
            )
        ]

    def __str__(self):
        return f"{self.student.matric_no} | {self.course.code} | {self.session}"

    @property
    def semester(self):
        return self.course.semester


class Result(models.Model):
    """Score for one registration. Lecturers enter it; the records officer approves it."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted for approval"
        APPROVED = "APPROVED", "Approved"

    registration = models.OneToOneField(
        Registration, on_delete=models.CASCADE, related_name="result"
    )
    # Scores are NULL until the lecturer enters them, so "not entered" is never confused with 0.
    ca_score = models.DecimalField(
        "CA score",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(settings.MAX_CA_SCORE)],
    )
    exam_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(settings.MAX_EXAM_SCORE)],
    )
    total = models.DecimalField(max_digits=5, decimal_places=2, editable=False, null=True, blank=True)
    grade = models.CharField(max_length=2, editable=False, blank=True)
    grade_point = models.PositiveSmallIntegerField(editable=False, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="results_entered",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["registration__course__code", "registration__student__matric_no"]

    def __str__(self):
        return f"{self.registration} => {self.total} ({self.grade})"

    def clean(self):
        if self.ca_score is not None and self.ca_score > settings.MAX_CA_SCORE:
            raise ValidationError({"ca_score": f"CA cannot exceed {settings.MAX_CA_SCORE}."})
        if self.exam_score is not None and self.exam_score > settings.MAX_EXAM_SCORE:
            raise ValidationError({"exam_score": f"Exam cannot exceed {settings.MAX_EXAM_SCORE}."})

    @property
    def is_complete(self):
        return self.ca_score is not None and self.exam_score is not None

    def save(self, *args, **kwargs):
        if self.is_complete:
            self.total = Decimal(self.ca_score) + Decimal(self.exam_score)
            self.grade, self.grade_point = compute_grade(self.total)
        else:
            self.total, self.grade, self.grade_point = None, "", 0
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """Immutable trail of who created, changed or deleted academic records."""

    class Action(models.TextChoices):
        CREATE = "CREATE", "Created"
        UPDATE = "UPDATE", "Updated"
        DELETE = "DELETE", "Deleted"
        LOGIN = "LOGIN", "Logged in"
        APPROVE = "APPROVE", "Approved"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    model_name = models.CharField(max_length=50)
    object_id = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField(max_length=255)
    changes = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.user} {self.action} {self.object_repr}"
