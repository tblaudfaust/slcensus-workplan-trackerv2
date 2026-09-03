"""
Django settings for census_tracker project.

All environment-specific values (secrets, database, email, scheduler) are
read from environment variables / a local .env file via django-environ.
See .env.example for the full list of supported variables.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    SCHEDULER_ENABLED=(bool, True),
    EMAIL_USE_SSL=(bool, False),
    REMINDER_DAYS=(list, ["1", "3", "7", "14"]),
    WORKSTREAM_OVERDUE_THRESHOLD=(int, 3),
)

# Reads a .env file in BASE_DIR if present; real deployments should set
# actual environment variables instead of shipping a .env file.
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# Render (and most PaaS platforms) terminate TLS at a load balancer and
# forward plain HTTP to the container, setting X-Forwarded-Proto so the app
# can tell the original request was HTTPS. Without this, Django thinks
# every request is insecure -- breaking secure cookies and SECURE_SSL_REDIRECT.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Render sets this automatically to the service's own *.onrender.com
# hostname; picking it up here means ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS
# don't need to be hand-maintained for the default Render URL.
_render_host = env("RENDER_EXTERNAL_HOSTNAME", default="")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.accounts",
    "apps.projects",
    "apps.activities",
    "apps.uploads",
    "apps.dashboard",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "census_tracker.urls"

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
                "apps.projects.context_processors.active_project",
                "apps.accounts.context_processors.role_flags",
            ],
        },
    },
]

WSGI_APPLICATION = "census_tracker.wsgi.application"

# Database
# DATABASE_URL, e.g. postgres://user:password@host:5432/dbname
# Defaults to a local SQLite file so the project runs with zero extra setup.
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "accounts:login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="Africa/Freetown")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Uploaded workbooks are held here only long enough for the preview/confirm
# step; nothing here needs to be, or should be, version-controlled.
UPLOAD_TMP_DIR = MEDIA_ROOT / "uploads_tmp"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Email ---------------------------------------------------------------
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
# Port 465 (implicit SSL) and port 587 (STARTTLS) are mutually exclusive in
# Django -- EMAIL_USE_SSL=True implies TLS is not also requested.
EMAIL_USE_SSL = env("EMAIL_USE_SSL")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=not EMAIL_USE_SSL)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Census Workplan Tracker <noreply@example.org>")

# --- Application-specific settings ---------------------------------------
SITE_NAME = env("SITE_NAME", default="Census Project Workplan Tracker")
SITE_URL = env("SITE_URL", default="http://localhost:8000")

# In-process scheduler (APScheduler) for deadline reminders + weekly digest.
# Disable when running tests or multiple app-server workers to avoid
# duplicate jobs firing; run `manage.py check_deadlines` / `send_weekly_digest`
# via external cron instead in that case.
SCHEDULER_ENABLED = env("SCHEDULER_ENABLED")

# Default reminder windows (days before an activity's end date) used to seed
# NotificationRule rows on first migrate; editable afterwards from the admin
# settings page.
REMINDER_DAYS_DEFAULT = [int(d) for d in env("REMINDER_DAYS")]
WORKSTREAM_OVERDUE_THRESHOLD_DEFAULT = env("WORKSTREAM_OVERDUE_THRESHOLD")

# --- Production hardening -------------------------------------------------
# Off by default so local dev (plain HTTP) and a not-yet-TLS-terminated
# deployment aren't broken out of the box; set SECURE_SSL_REDIRECT=True once
# the app is served behind HTTPS (directly or via a TLS-terminating proxy).
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
    SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
    CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
