# Centralized Student Academic Records Database System

A web-based system for managing a university department's student academic records in one central database. It covers:

- student bio-data and passport photos;
- course registration;
- result entry and approval;
- automatic GPA/CGPA;
- promotion and graduation;
- transcript generation.

Access is controlled by role, and every change is recorded in an audit trail.

Built with **Python 3.11** and **Django 5.2**. It runs on SQLite out of the box, and on MySQL or PostgreSQL for larger deployments. Final-year project.

## Features

| Area | What it does |
|---|---|
| **First-time setup** | A brand-new installation opens a setup page. There you enter the real institution, faculty, department and current session, and create the administrator account. No demo data is involved. |
| **Roles** | Administrator, Records Officer, Lecturer and Student. Each sees only their own menu and data. |
| **Accounts and passwords** | New users get a temporary password, shown once, and **must change it at first login**. Staff can **reset** forgotten passwords. Optional **"Forgot password" by email**. Accounts **lock for 15 minutes after 5 failed logins**. |
| **Student records** | Create, view, update and delete bio-data, including a passport photo. Search, filters and CSV export. |
| **Bulk import** | Import real students and courses from Excel/CSV templates. The whole file is checked first, and nothing is imported if any row is wrong. After a student import, printable **login slips** can be downloaded once. |
| **Academic structure** | Institution settings (name, address, logo, registrar), department, academic sessions, and courses with units, level, semester and lecturer. |
| **Course registration** | Students register the current semester's courses. Failed courses are added automatically as carry-overs. The unit limit is enforced, and registration can be opened or closed. |
| **Results** | Lecturers enter CA and exam scores on screen or by CSV upload. Results go Draft → Submitted → Approved. Approved results are locked. Blank scores stay "not entered" and are never counted as 0. |
| **GPA / CGPA** | Unit-weighted, on a 5.0 scale, with the class of degree. |
| **Promotion and graduation** | One click promotes all active students to the next level, and can only run once per session. Eligible final-year students can be marked as graduated. |
| **Transcripts** | Printable HTML and PDF, with the institution logo, student photo and registrar's name. |
| **Audit trail** | Every create, update, delete, approval, login and backup is logged with user, time, IP address and the changed fields. Read-only. |
| **Backups** | One-click backup download, plus a `backup` command for scheduled daily backups. |
| **Security** | Hashed passwords, CSRF protection, session timeout, role checks on every view, and photos served only to authorised users. Production settings refuse to start without a secret key. |

## Grading policy (configurable in `config/settings.py`)

| Score | Grade | Point |
|---|---|---|
| 70-100 | A | 5 |
| 60-69 | B | 4 |
| 50-59 | C | 3 |
| 45-49 | D | 2 |
| 40-44 | E | 1 |
| 0-39 | F | 0 |

CA is out of 30 and the exam out of 70.
GPA = Σ(units × grade point) ÷ Σ(units).

Degree classes: First Class ≥ 4.50, 2:1 ≥ 3.50, 2:2 ≥ 2.40, Third ≥ 1.50, Pass ≥ 1.00.

## Quick start (development, Windows / VS Code)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000. The first-time setup page appears.

### Getting real data in (after setup)

1. **Staff Accounts:** create each lecturer. Give them their temporary password privately.
2. **Courses → Import from CSV:** download the template, fill in your department's courses in Excel, save as CSV and upload.
3. **Import Students:** same process, then download and hand out the login slips.
4. **Students** sign in, change their password and register courses.
5. **Lecturers** enter results; the **Records Officer** approves them.

### Putting it into real use

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**. It covers running on a department computer for the whole office network, or online on PythonAnywhere, plus email, backups and a go-live checklist.

Production server: `python serve.py`, which uses Waitress.

### Demo data (for presentations only)

```bash
python manage.py seed_demo
```

This loads 40 fictional students and 32 courses. It works only with `DEBUG=True` on an empty database. **Never use it on a real installation.**

## Running the tests

```bash
python manage.py test
```

The 29 automated tests cover:

- grading, GPA weighting and the audit trail;
- role-based access;
- registration rules, and the enter → submit → approve workflow with locking;
- blank-score handling, CSV result upload and transcripts;
- first-time setup;
- temporary passwords with forced change, login lockout and password resets;
- student and course import (including all-or-nothing validation);
- promotion, graduation and backups.

## Project structure

```
config/        settings, URL routes
accounts/      User model with roles, setup wizard, login lockout, password rules, staff management
academics/     Institution, Department, AcademicSession, Course
records/       Student, Registration, Result, AuditLog; views, grading, importers, PDF transcript, audit signals
  management/commands/backup.py      scheduled backups
  management/commands/seed_demo.py   demo data (development only)
templates/     Bootstrap 5 HTML templates
static/        CSS
docs/          SYSTEM_DESIGN.md (ERD, use cases), DEPLOYMENT.md (going live)
serve.py       production server (Waitress)
```
