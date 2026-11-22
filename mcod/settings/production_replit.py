"""Production settings for the Replit VM deployment."""

import hashlib
import hmac
import os

os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379")
os.environ.setdefault("ELASTICSEARCH_HOSTS", "127.0.0.1:9200")
os.environ.setdefault("RABBITMQ_HOST", "127.0.0.1:5672")
os.environ.setdefault("ENVIRONMENT", "prod")

from mcod.settings.base import *  # noqa: E402,F403

DEBUG = False
ENVIRONMENT = "prod"
SECRET_KEY = os.environ["SESSION_SECRET"]
JWT_SECRET_KEY = SECRET_KEY
FIELD_ENCRYPTION_KEYS = env.list("FIELD_ENCRYPTION_KEYS", default=[])  # noqa: F405
if not FIELD_ENCRYPTION_KEYS:
    FIELD_ENCRYPTION_KEYS = [
        hmac.new(
            SECRET_KEY.encode(), b"mcod-replit-development-fields", hashlib.sha256
        ).hexdigest()
    ]

DATABASES = {"default": env.db("DATABASE_URL")}  # noqa: F405
DATABASES["default"]["ATOMIC_REQUESTS"] = True

_configured_hosts = [
    host.strip()
    for host in os.environ.get("MCOD_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]
ALLOWED_HOSTS = [".replit.app", ".replit.dev"] + _configured_hosts
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("MCOD_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "mcod_replit_session"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_NAME = "csrftoken"

API_URL = os.environ.get("API_URL", "/api")
API_URL_INTERNAL = os.environ.get("API_URL_INTERNAL", "http://127.0.0.1:8000")
AED_INTEGRATION_SECRET = os.environ.get("AED_INTEGRATION_SECRET", "")
AED_REQUIRE_HTTPS = True
REPLIT_APP_STORAGE_ENABLED = (
    os.environ.get("MCOD_APP_STORAGE_ENABLED", "").lower() in ("1", "true", "yes")
)

USE_RDF_DB = False
DISCOURSE_FORUM_ENABLED = False
UNLEASH_ENABLED = False
for logger in LOGGING["loggers"].values():  # noqa: F405
    logger["handlers"] = ["console"]
LOGGING["handlers"] = {"console": LOGGING["handlers"]["console"]}  # noqa: F405
LOGGING["root"] = {"handlers": ["console"], "level": "WARNING"}
