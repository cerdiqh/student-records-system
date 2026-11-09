"""
Bulk import of real department data from CSV files.

Every file is checked completely first. If any row has a problem, nothing is
imported and all problems are reported, so a half-imported file never happens.
"""
import csv
import io
from datetime import datetime

from django.db import transaction

from academics.models import AcademicSession, Course, Level, Semester
from accounts.models import User
from accounts.security import generate_temp_password

from .models import Student

STUDENT_COLUMNS = ["matric_no", "surname", "first_name", "other_names", "gender", "level", "entry_session",
                   "email", "phone", "date_of_birth", "state_of_origin", "address", "guardian_name", "guardian_phone"]
STUDENT_REQUIRED = {"matric_no", "surname", "first_name", "gender", "level", "entry_session"}

COURSE_COLUMNS = ["code", "title", "units", "level", "semester", "lecturer_username", "elective"]
COURSE_REQUIRED = {"code", "title", "units", "level", "semester"}

VALID_LEVELS = {lvl.value for lvl in Level}


def read_csv(uploaded_file, required):
    """Return (rows, error). Each row is (line_number, {lowercase_column: stripped_value})."""
    raw = uploaded_file.read()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    reader = csv.DictReader(io.StringIO(text))
    headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    missing = required - headers
    if missing:
        return [], f"The file is missing these columns: {', '.join(sorted(missing))}."
    rows = []
    for line, raw_row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
        if any(row.values()):
            rows.append((line, row))
    if not rows:
        return [], "The file has no data rows."
    return rows, None


def _parse_date(value):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError


def import_students(uploaded_file, department):
    """Returns (created, errors). created = list of (matric_no, full name, temporary password)."""
    rows, error = read_csv(uploaded_file, STUDENT_REQUIRED)
    if error:
        return [], [error]
    sessions = {s.name: s for s in AcademicSession.objects.all()}
    existing = {u.lower() for u in User.objects.values_list("username", flat=True)}
    seen, errors, valid = set(), [], []

    for line, r in rows:
        problems = []
        matric = " ".join(r.get("matric_no", "").upper().split())
        if not matric:
            problems.append("matric_no is empty")
        elif matric.lower() in existing:
            problems.append(f"{matric} already exists in the system")
        elif matric in seen:
            problems.append(f"{matric} appears more than once in the file")
        for col in ("surname", "first_name"):
            if not r.get(col):
                problems.append(f"{col} is empty")
        gender = r.get("gender", "").upper()[:1]
        if gender not in ("M", "F"):
            problems.append("gender must be M or F")
        try:
            level = int(r.get("level", ""))
            if level not in VALID_LEVELS:
                raise ValueError
        except ValueError:
            level = None
            problems.append("level must be 100, 200, 300, 400 or 500")
        session = sessions.get(r.get("entry_session", ""))
        if session is None:
            problems.append(f"entry_session '{r.get('entry_session', '')}' does not exist (create it under Academic Sessions first)")
        dob = None
        if r.get("date_of_birth"):
            try:
                dob = _parse_date(r["date_of_birth"])
            except ValueError:
                problems.append("date_of_birth must look like 2004-03-21 or 21/03/2004")
        if problems:
            errors.append(f"Row {line}: " + "; ".join(problems))
            continue
        seen.add(matric)
        valid.append(dict(matric=matric, surname=r["surname"], first=r["first_name"], other=r.get("other_names", ""),
                          gender=gender, level=level, session=session, email=r.get("email", ""),
                          phone=r.get("phone", ""), dob=dob, state=r.get("state_of_origin", ""),
                          address=r.get("address", ""), guardian=r.get("guardian_name", ""),
                          guardian_phone=r.get("guardian_phone", "")))

    if errors:
        return [], errors

    created = []
    with transaction.atomic():
        for v in valid:
            temp = generate_temp_password()
            user = User(username=v["matric"], first_name=f"{v['first']} {v['other']}".strip(),
                        last_name=v["surname"], email=v["email"], phone=v["phone"],
                        role=User.Role.STUDENT, must_change_password=True)
            user.set_password(temp)
            user.save()
            Student.objects.create(user=user, matric_no=v["matric"], department=department, level=v["level"],
                                   entry_session=v["session"], gender=v["gender"], date_of_birth=v["dob"],
                                   state_of_origin=v["state"], address=v["address"], guardian_name=v["guardian"],
                                   guardian_phone=v["guardian_phone"])
            created.append((v["matric"], f"{v['surname'].upper()}, {user.first_name}", temp))
    return created, []


def import_courses(uploaded_file, department):
    """Creates new courses and updates existing ones (matched by code). Returns (created, updated, errors)."""
    rows, error = read_csv(uploaded_file, COURSE_REQUIRED)
    if error:
        return 0, 0, [error]
    lecturers = {u.username.lower(): u for u in User.objects.filter(role=User.Role.LECTURER)}
    seen, errors, valid = set(), [], []
    for line, r in rows:
        problems = []
        code = " ".join(r.get("code", "").upper().split())
        if not code:
            problems.append("code is empty")
        elif code in seen:
            problems.append(f"{code} appears more than once in the file")
        if not r.get("title"):
            problems.append("title is empty")
        try:
            units = int(r.get("units", ""))
            if not 1 <= units <= 6:
                raise ValueError
        except ValueError:
            units = None
            problems.append("units must be a whole number from 1 to 6")
        try:
            level = int(r.get("level", ""))
            if level not in VALID_LEVELS:
                raise ValueError
        except ValueError:
            level = None
            problems.append("level must be 100, 200, 300, 400 or 500")
        sem = r.get("semester", "").upper()
        semester = {"FIRST": Semester.FIRST, "1": Semester.FIRST, "1ST": Semester.FIRST,
                    "SECOND": Semester.SECOND, "2": Semester.SECOND, "2ND": Semester.SECOND}.get(sem)
        if semester is None:
            problems.append("semester must be FIRST or SECOND (or 1 / 2)")
        lecturer = None
        if r.get("lecturer_username"):
            lecturer = lecturers.get(r["lecturer_username"].lower())
            if lecturer is None:
                problems.append(f"no lecturer account with username '{r['lecturer_username']}'")
        elective = r.get("elective", "").lower() in ("yes", "y", "true", "1", "e", "elective")
        if problems:
            errors.append(f"Row {line}: " + "; ".join(problems))
            continue
        seen.add(code)
        valid.append(dict(code=code, title=r["title"], units=units, level=level, semester=semester,
                          lecturer=lecturer, is_elective=elective))
    if errors:
        return 0, 0, errors

    created = updated = 0
    with transaction.atomic():
        for v in valid:
            code = v.pop("code")
            if v["lecturer"] is None:
                v.pop("lecturer")  # keep the current lecturer when the column is blank
            _, was_created = Course.objects.update_or_create(code=code, defaults={**v, "department": department})
            created += was_created
            updated += not was_created
    return created, updated, []
