# Centralized Student Academic Records Database System

A web-based system for managing student academic records in a university department: bio-data, course registration, result entry and approval, automatic GPA/CGPA calculation, and transcript generation. All records sit in one central database, protected by role-based access control and an audit trail.

Built with **Python 3.11**, **Django 5.2** and **SQLite** by default. PostgreSQL or MySQL can be used instead. Final-year project.

## Features

| Area | What it does |
|---|---|
| **Authentication and roles** | Four roles: Administrator, Records Officer, Lecturer and Student. Each role sees only its own menu and data. |
| **Student records** | Create, view, update and delete student bio-data. Each student gets a login account (username = matric number). Search, filters and CSV export. |
| **Academic structure** | Department, academic sessions (one marked *current*), and courses with units, level, semester and assigned lecturer. |
| **Course registration** | Students register for the current semester's courses. Failed courses show up automatically as carry-overs. A per-semester unit limit is enforced, and the records office can open or close registration. |
| **Result management** | Lecturers enter CA and exam scores on screen or by CSV upload. Totals, grades and grade points are computed automatically. Results go from Draft to Submitted to Approved; once approved they are locked. |
| **GPA / CGPA** | Unit-weighted GPA per semester and cumulative CGPA on a 5.0 scale, plus the current class of degree. |
| **Transcripts** | Printable HTML transcript and a downloadable PDF built with ReportLab. Only approved results appear. |
| **Audit trail** | Every create, update, delete, approval and login is logged with user, time, IP address and the changed fields. The log is read-only. |
| **Security** | Hashed passwords, CSRF protection, session timeout, role checks on every view, and server-side score validation. |

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

## Getting started (Windows, VS Code)

```bash
# 1. Open the folder in VS Code, then in the terminal:
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. Create the database
python manage.py migrate

# 3. (Optional) Load demo data: 40 students, 32 courses, 4 sessions of results
python manage.py seed_demo

# 4. Run
python manage.py runserver
```

Then open http://127.0.0.1:8000.

### Demo accounts (created by `seed_demo`)

| Role | Username | Password |
|---|---|---|
| Administrator | `admin` | `Admin@1234` |
| Records Officer | `registrar` | `Pass@1234` |
| Lecturer | `lecturer1` … `lecturer4` | `Pass@1234` |
| Student | `CSC/2024/001` (any matric number) | `Pass@1234` |

These are demo passwords. Change them, or start without demo data, for any real use. Without demo data, create the first admin account with `python manage.py createsuperuser`.

### Using MySQL (XAMPP) or PostgreSQL

1. Copy `.env.example` to `.env`.
2. Set `DB_ENGINE=mysql` (or `postgresql`) and fill in the `DB_*` values.
3. Install the matching driver: `pip install mysqlclient` or `pip install "psycopg[binary]"`.
4. Create an empty database named `sars`, then run `python manage.py migrate`.

## Running the tests

```bash
python manage.py test
```

The tests cover grade boundaries, GPA weighting, the audit trail, role-based access, course registration rules, the enter → submit → approve workflow, the locking of approved results, CSV upload, student creation and PDF transcripts.

## Project structure

```
config/        settings, URL routes
accounts/      custom User model with roles, staff management, access-control decorators
academics/     Department, AcademicSession, Course
records/       Student, Registration, Result, AuditLog; views, grading, PDF transcript, audit signals
  management/commands/seed_demo.py   demo data loader
templates/     Bootstrap 5 HTML templates
static/        CSS
docs/          system design (ERD, use cases, architecture)
```

See [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md) for the database design and diagrams.
