"""Production settings for the Replit VM deployment."""

import os

os.environ.setdefault("ENVIRONMENT", "prod")

from mcod.settings.replit_common import *  # noqa: E402,F403

DEBUG = False
ENVIRONMENT = "prod"

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
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

API_URL = os.environ.get("API_URL", "/api")
