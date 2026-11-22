"""Shared application configuration for development and publishing on Replit."""

import hashlib
import hmac
import os

from psycopg2.extensions import libpq_version

from mcod.settings.database_compat import neon_compatible_database

os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379")
os.environ.setdefault("ELASTICSEARCH_HOSTS", "127.0.0.1:9200")
os.environ.setdefault("RABBITMQ_HOST", "127.0.0.1:5672")

from mcod.settings.base import *  # noqa: E402,F403

SECRET_KEY = os.environ["SESSION_SECRET"]
JWT_SECRET_KEY = SECRET_KEY
FIELD_ENCRYPTION_KEYS = env.list("FIELD_ENCRYPTION_KEYS", default=[])  # noqa: F405
if not FIELD_ENCRYPTION_KEYS:
    FIELD_ENCRYPTION_KEYS = [
        hmac.new(
            SECRET_KEY.encode(), b"mcod-replit-development-fields", hashlib.sha256
        ).hexdigest()
    ]

DATABASES = {
    "default": neon_compatible_database(env.db("DATABASE_URL"), libpq_version())  # noqa: F405
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "mcod_replit_session"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_NAME = "csrftoken"
API_URL_INTERNAL = os.environ.get("API_URL_INTERNAL", "http://127.0.0.1:8000")
AED_INTEGRATION_SECRET = os.environ.get("AED_INTEGRATION_SECRET", "")
AED_REQUIRE_HTTPS = True
REPLIT_APP_STORAGE_ENABLED = (
    os.environ.get("MCOD_APP_STORAGE_ENABLED", "").lower() in ("1", "true", "yes")
)

EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = str(ROOT_DIR.path("generated-artifacts", "mail"))  # noqa: F405
USE_RDF_DB = False
HEALTH_CHECK = False
DISCOURSE_FORUM_ENABLED = False
UNLEASH_ENABLED = False
ELASTICSEARCH_DSL_INDEX_SETTINGS = {"number_of_shards": 1, "number_of_replicas": 0}
ELASTICSEARCH_HISTORIES_IDX_SETTINGS = {"number_of_shards": 1, "number_of_replicas": 0}
FIXTURE_DIRS = [str(DATA_DIR.path("initial_data"))]  # noqa: F405
for logger in LOGGING["loggers"].values():  # noqa: F405
    logger["handlers"] = ["console"]
LOGGING["handlers"] = {"console": LOGGING["handlers"]["console"]}  # noqa: F405
LOGGING["root"] = {"handlers": ["console"], "level": "WARNING"}
