"""
Django settings for litigation-intelligence prototype.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-in-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "app.storage",
    "app.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": os.environ.get("DB_NAME", "litigation_db"),
#         "USER": os.environ.get("DB_USER", "litigation_user"),
#         "PASSWORD": os.environ.get("DB_PASSWORD", "litigation_pass"),
#         "HOST": os.environ.get("DB_HOST", "localhost"),
#         "PORT": os.environ.get("DB_PORT", "5432"),
#     }
# }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

STATIC_URL = "/static/"
TEMPLATES = []

# Pipeline settings
COURTLISTENER_API_TOKEN = os.environ.get("COURTLISTENER_API_TOKEN", "")
COURTLISTENER_BASE_URL = os.environ.get(
    "COURTLISTENER_BASE_URL", "https://www.courtlistener.com/api/rest/v3"
)
TARGET_COURT = os.environ.get("TARGET_COURT", "nysd")  # SDNY court code
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
PDF_TEXT_MIN_LENGTH = int(os.environ.get("PDF_TEXT_MIN_LENGTH", "500"))
SUMMARY_MAX_CHARS = int(os.environ.get("SUMMARY_MAX_CHARS", "2000"))
DATA_DIR = BASE_DIR / "data" / "filings"
