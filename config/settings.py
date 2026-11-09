"""
Django settings for the Centralized Student Academic Records Database System (SARS).

Configuration is read from environment variables (or a local .env file) so the
same code runs on a developer laptop with SQLite and on a server with
PostgreSQL or MySQL. See .env.example.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.environ.get(
    "SECRET_KEY", "dev-only-insecure-key-change-me-in-production"
)
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Project apps
    "accounts",
    "academics",
    "records",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Records which user made each change, for the audit trail.
    "records.middleware.CurrentUserMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "academics.context_processors.current_session",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# DB_ENGINE: sqlite (default) | postgresql | mysql
# ---------------------------------------------------------------------------
DB_ENGINE = os.environ.get("DB_ENGINE", "sqlite").lower()
if DB_ENGINE in ("postgresql", "postgres"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "sars"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
elif DB_ENGINE == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("DB_NAME", "sars"),
            "USER": os.environ.get("DB_USER", "root"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "Africa/Lagos")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Session security
SESSION_COOKIE_AGE = 60 * 60 * 2  # log users out after 2 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ---------------------------------------------------------------------------
# Institution details (shown on transcripts)
# ---------------------------------------------------------------------------
INSTITUTION_NAME = os.environ.get("INSTITUTION_NAME", "Federal University of Technology")
DEPARTMENT_NAME = os.environ.get("DEPARTMENT_NAME", "Department of Computer Science")

# ---------------------------------------------------------------------------
# Grading policy (5.0 scale). Edit here to match your institution.
# Each entry: (minimum total score, letter grade, grade point)
# ---------------------------------------------------------------------------
GRADING_SCALE = [
    (70, "A", 5),
    (60, "B", 4),
    (50, "C", 3),
    (45, "D", 2),
    (40, "E", 1),
    (0, "F", 0),
]
MAX_CA_SCORE = 30
MAX_EXAM_SCORE = 70

# Degree classification by CGPA: (minimum CGPA, class)
DEGREE_CLASSES = [
    (4.50, "First Class Honours"),
    (3.50, "Second Class Honours (Upper Division)"),
    (2.40, "Second Class Honours (Lower Division)"),
    (1.50, "Third Class Honours"),
    (1.00, "Pass"),
    (0.00, "Fail"),
]

# Maximum credit units a student may register per semester
MAX_UNITS_PER_SEMESTER = 24
