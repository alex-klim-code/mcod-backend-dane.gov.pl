"""Development configuration for the imported project on Replit."""

import hashlib
import hmac
import os

# Set service defaults before base.py constructs its caches and search clients.
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379")
os.environ.setdefault("ELASTICSEARCH_HOSTS", "127.0.0.1:9200")
os.environ.setdefault("RABBITMQ_HOST", "127.0.0.1:5672")
os.environ.setdefault("ENVIRONMENT", "local")

from mcod.settings.base import *  # noqa: E402,F403

DEBUG = True
ENVIRONMENT = "local"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".replit.dev"]
if os.environ.get("REPLIT_DEV_DOMAIN"):
    ALLOWED_HOSTS.append(os.environ["REPLIT_DEV_DOMAIN"])

# Reuse the workspace's securely provisioned secret, never the upstream default.
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
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = None
SESSION_COOKIE_NAME = "mcod_replit_session"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = None
CSRF_COOKIE_NAME = "csrftoken"
# The Replit proxy keeps the browser's :5000 port in the HTTPS Referer, while
# Django can see the same host without that external port. Django 2.2 compares
# trusted origins as host strings, so trust only this Repl's preview hostname.
_preview_domain = os.environ.get("REPLIT_DEV_DOMAIN", "").strip()
CSRF_TRUSTED_ORIGINS = (
    [origin for origin in (_preview_domain, f"{_preview_domain}:5000") if _preview_domain]
)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
API_URL = os.environ.get(
    "API_URL", "https://{}:5000/api".format(_preview_domain) if _preview_domain else "/api"
)
AED_INTEGRATION_SECRET = os.environ.get("AED_INTEGRATION_SECRET", "")
AED_REQUIRE_HTTPS = True
REPLIT_APP_STORAGE_ENABLED = (
    os.environ.get("MCOD_APP_STORAGE_ENABLED", "").lower() in ("1", "true", "yes")
)

EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = str(ROOT_DIR.path("generated-artifacts", "mail"))  # noqa: F405
AXES_ENABLED = False
SILENCED_SYSTEM_CHECKS = ["axes.W002"]
MIDDLEWARE = [m for m in MIDDLEWARE if m != "axes.middleware.AxesMiddleware"]  # noqa: F405
MIDDLEWARE.insert(0, "mcod.settings.replit.PreviewCookiesMiddleware")
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


class PreviewCookiesMiddleware:
    """Django 2.2 predates SameSite=None support; add it after cookie creation."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        for name in (SESSION_COOKIE_NAME, CSRF_COOKIE_NAME):  # noqa: F405
            if name in response.cookies:
                response.cookies[name]["samesite"] = "None"
                response.cookies[name]["secure"] = True
        return response
