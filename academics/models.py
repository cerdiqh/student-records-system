from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Semester(models.TextChoices):
    FIRST = "FIRST", "First Semester"
    SECOND = "SECOND", "Second Semester"


class Level(models.IntegerChoices):
    L100 = 100, "100 Level"
    L200 = 200, "200 Level"
    L300 = 300, "300 Level"
    L400 = 400, "400 Level"
    L500 = 500, "500 Level"


class Institution(models.Model):
    """Single row holding the school's details (shown on every page and on transcripts)."""

    name = models.CharField("Institution name", max_length=200)
    address = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    logo = models.ImageField(upload_to="institution/", blank=True,
                             help_text="PNG or JPG, max 1 MB. Printed on transcripts.")
    registrar_name = models.CharField(
        max_length=150, blank=True, help_text="Name printed under the signature line on transcripts."
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce a single row
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.filter(pk=1).first()


class Department(models.Model):
    name = models.CharField(max_length=150, unique=True, help_text="e.g. Computer Science")
    code = models.CharField(max_length=10, unique=True, help_text="e.g. CSC")
    faculty = models.CharField(max_length=150)
    final_level = models.IntegerField(
        choices=Level.choices, default=Level.L400,
        help_text="Final year of the programme (400 for a 4-year degree, 500 for 5 years).",
    )
    head = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headed_departments",
        limit_choices_to={"role": "LECTURER"},
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AcademicSession(models.Model):
    """An academic year, e.g. 2025/2026. Exactly one session is 'current'."""

    name = models.CharField(max_length=9, unique=True, help_text="Format: 2025/2026")
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    current_semester = models.CharField(
        max_length=10, choices=Semester.choices, default=Semester.FIRST
    )
    registration_open = models.BooleanField(
        default=True, help_text="Students may register courses while this is on."
    )
    students_promoted = models.BooleanField(
        default=False, editable=False,
        help_text="Set once students have been promoted into this session (prevents promoting twice).",
    )

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError("End date must be after start date.")

    def save(self, *args, **kwargs):
        # Only one session may be current at a time.
        if self.is_current:
            AcademicSession.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_current(cls):
        return cls.objects.filter(is_current=True).first()


class Course(models.Model):
    code = models.CharField(max_length=10, unique=True, help_text="e.g. CSC 301")
    title = models.CharField(max_length=200)
    units = models.PositiveSmallIntegerField(default=3)
    level = models.IntegerField(choices=Level.choices)
    semester = models.CharField(max_length=10, choices=Semester.choices)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="courses")
    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses_taught",
        limit_choices_to={"role": "LECTURER"},
    )
    is_elective = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["level", "semester", "code"]

    def __str__(self):
        return f"{self.code} - {self.title}"

    def clean(self):
        if self.units is not None and not 1 <= self.units <= 6:
            raise ValidationError({"units": "Credit units must be between 1 and 6."})
