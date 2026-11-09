# System Design

This document describes the design of the Centralized Student Academic Records Database System. You can use it as the basis for the system analysis and design chapter of the project report.

## 1. Problem statement

In many departments, student records are kept in paper files and separate spreadsheets held by different offices. This causes:

- duplicated and inconsistent records;
- slow, error-prone GPA calculation and transcript preparation;
- no single source of truth;
- weak access control, so results can be changed without trace;
- lost records and difficult retrieval.

## 2. Objectives

1. Design a normalised relational database that stores all student academic records centrally.
2. Implement a web application with self sign-up, email verification and role-based access for administrators, lecturers and students.
3. Automate grade, GPA and CGPA computation and transcript generation.
4. Enforce data integrity through validation, a result approval workflow and a tamper-evident audit trail.

## 3. Methodology

The system follows a three-tier **Model-View-Template (MVT)** architecture, implemented with Django:

```mermaid
flowchart LR
    U[Browser<br/>Bootstrap 5 UI] -- HTTP/HTTPS --> V[Django Views<br/>role checks, business rules]
    V --> T[Templates<br/>HTML / PDF]
    V --> M[Models / ORM]
    M --> DB[(Relational DB<br/>SQLite / MySQL / PostgreSQL)]
    M -. signals .-> A[Audit Log]
```

- **Presentation tier:** HTML templates styled with Bootstrap 5, plus PDF output through ReportLab.
- **Application tier:** Django views that enforce access control, validation, grading rules and the approval workflow.
- **Data tier:** a relational database reached through the Django ORM, using parameterised queries that guard against SQL injection.

The development approach was incremental (iterative waterfall): requirements → database design → implementation module by module → testing.

## 4. Users and roles

| Role | Permissions |
|---|---|
| Administrator | First person to sign up. Approves lecturer sign-ups; manages students, courses and sessions; approves or returns results; views the audit log; unlocks approved results; takes backups. |
| Lecturer | Signs up, then waits for the administrator's approval. Views assigned courses. Enters and uploads scores and submits them for approval. |
| Student | Signs up with matric number and email and gets access immediately. Views own profile and results, registers courses while registration is open, and downloads own transcript. |

## 4b. Sign-up and account activation

```mermaid
flowchart TD
    A[Visitor opens the site] --> B{Any administrator yet?}
    B -- No --> C[Administrator sign-up<br/>institution, department, session, admin account]
    B -- Yes --> D{Student or Lecturer?}
    D -- Student --> E[Student sign-up<br/>matric no, level, email, password]
    D -- Lecturer --> F[Lecturer sign-up<br/>staff ID, email, password]
    C & E & F --> G[6-digit code emailed]
    G --> H{Code correct within 15 min, max 5 tries?}
    H -- No --> G
    H -- Yes, admin or student --> I[Dashboard]
    H -- Yes, lecturer --> J[Waiting for approval<br/>admin is emailed]
    J -- Admin approves --> I
    J -- Admin rejects --> K[Account disabled]
```

## 5. Use case diagram

```mermaid
flowchart LR
    Admin((Administrator))
    Lec((Lecturer))
    Stu((Student))

    subgraph SARS [Student Academic Records System]
      UC0[Sign up + confirm email by code]
      UC1[Log in / change password]
      UC12[Approve lecturer sign-ups]
      UC2[Manage staff accounts]
      UC3[View audit log]
      UC4[Manage student records]
      UC5[Manage courses and sessions]
      UC6[Register courses]
      UC7[Enter / upload scores]
      UC8[Submit results]
      UC9[Approve / return results]
      UC10[View results and CGPA]
      UC11[Generate transcript]
    end

    Admin --- UC0 & UC1 & UC2 & UC3 & UC4 & UC5 & UC9 & UC11 & UC12
    Lec --- UC0 & UC1 & UC7 & UC8
    Stu --- UC0 & UC1 & UC6 & UC10 & UC11
```

## 6. Database design (ERD)

```mermaid
erDiagram
    USER ||--o| STUDENT : "has profile"
    USER ||--o{ COURSE : "teaches"
    DEPARTMENT ||--o{ COURSE : offers
    DEPARTMENT ||--o{ STUDENT : enrols
    ACADEMIC_SESSION ||--o{ STUDENT : "entry session"
    ACADEMIC_SESSION ||--o{ REGISTRATION : in
    STUDENT ||--o{ REGISTRATION : makes
    COURSE ||--o{ REGISTRATION : "registered in"
    REGISTRATION ||--o| RESULT : produces
    USER ||--o{ RESULT : "enters / approves"
    USER ||--o{ AUDIT_LOG : performs

    USER {
        int id PK
        string username UK
        string password "hashed (PBKDF2)"
        string first_name
        string last_name
        string email
        string role "ADMIN|LECTURER|STUDENT"
        bool email_verified
        bool is_approved
        string email_code "hashed 6-digit code"
    }
    DEPARTMENT {
        int id PK
        string name UK
        string code UK
        string faculty
        int head_id FK
    }
    ACADEMIC_SESSION {
        int id PK
        string name UK "2025/2026"
        date start_date
        date end_date
        bool is_current
        string current_semester
        bool registration_open
    }
    COURSE {
        int id PK
        string code UK
        string title
        int units
        int level
        string semester
        int department_id FK
        int lecturer_id FK
        bool is_elective
        bool is_active
    }
    STUDENT {
        int id PK
        int user_id FK, UK
        string matric_no UK
        int department_id FK
        int level
        int entry_session_id FK
        string gender
        date date_of_birth
        string status
    }
    REGISTRATION {
        int id PK
        int student_id FK
        int course_id FK
        int session_id FK
        datetime registered_at
    }
    RESULT {
        int id PK
        int registration_id FK, UK
        decimal ca_score
        decimal exam_score
        decimal total
        string grade
        int grade_point
        string status "DRAFT|SUBMITTED|APPROVED"
        int entered_by FK
        int approved_by FK
    }
    AUDIT_LOG {
        int id PK
        int user_id FK
        string action
        string model_name
        string object_repr
        text changes
        string ip_address
        datetime timestamp
    }
```

**Normalisation:** the schema is in Third Normal Form.

- A student's course history is held in `REGISTRATION`, with a unique constraint on (student, course, session) that prevents duplicate registrations.
- Scores live in `RESULT`, one per registration.
- `total`, `grade` and `grade_point` are derived when a result is saved, and are stored so transcripts can be generated quickly.
- GPA and CGPA are never stored. They are always computed from approved results, so they cannot become inconsistent.

## 7. Key processes

### Result workflow

```mermaid
stateDiagram-v2
    [*] --> Draft: lecturer enters scores
    Draft --> Draft: save draft / CSV upload
    Draft --> Submitted: lecturer submits
    Submitted --> Draft: administrator returns for correction
    Submitted --> Approved: administrator approves
    Approved --> Draft: administrator unlocks (logged)
    Approved --> [*]: appears on transcript and in CGPA
```

### GPA computation

```
GPA  = Σ (course units × grade point) / Σ (course units)   for one semester
CGPA = same formula over all approved results to date
```

## 8. Security measures

- Passwords hashed with PBKDF2 (Django default), with password strength validators.
- Role-based access checked on the server for every view (`accounts/decorators.py`); students can access only their own records.
- CSRF tokens on all forms; sessions expire after 2 hours or when the browser closes.
- ORM queries are parameterised, which prevents SQL injection.
- Server-side validation of all scores (CA 0–30, exam 0–70) and of uploaded files (CSV only, up to 2 MB).
- Approved results are locked against editing.
- A read-only audit log records every change, with the old value, new value, user and IP address.

## 9. Testing

Automated tests live in `records/tests.py` and run with `python manage.py test`:

| Test | Purpose |
|---|---|
| Grade boundaries | Each score maps to the correct grade and grade point |
| GPA weighting | GPA is weighted by units; unapproved results are excluded |
| Unique registration | Database rejects duplicate registrations |
| Audit trail | Updates are logged with field changes |
| Access control | Login required; students and lecturers limited correctly |
| Course registration | Unit limit respected; closed registration blocks students |
| Result workflow | Enter → submit → approve; approved results locked |
| Validation | Out-of-range scores rejected |
| CSV upload | Bulk scores applied; unknown matric numbers reported |
| Student creation | Creates linked login account |
| Transcript | HTML and PDF generated |
