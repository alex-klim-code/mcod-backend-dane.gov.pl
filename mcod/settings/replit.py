"""Development configuration for the imported project on Replit."""

import os

os.environ.setdefault("ENVIRONMENT", "local")

from mcod.settings.replit_common import *  # noqa: E402,F403

DEBUG = True
ENVIRONMENT = "local"
SESSION_COOKIE_SAMESITE = None
CSRF_COOKIE_SAMESITE = None
# The Replit proxy keeps the browser's :5000 port in the HTTPS Referer, while
# Django can see the same host without that external port. Django 2.2 compares
# trusted origins as host strings, so trust only this Repl's preview hostname.
_preview_domain = os.environ.get("REPLIT_DEV_DOMAIN", "").strip()
CSRF_TRUSTED_ORIGINS = (
    [origin for origin in (_preview_domain, f"{_preview_domain}:5000") if _preview_domain]
)
API_URL = os.environ.get(
    "API_URL", "https://{}/api".format(_preview_domain) if _preview_domain else "/api"
)

AXES_ENABLED = False
SILENCED_SYSTEM_CHECKS = ["axes.W002"]
MIDDLEWARE = [m for m in MIDDLEWARE if m != "axes.middleware.AxesMiddleware"]  # noqa: F405
MIDDLEWARE.insert(0, "mcod.settings.replit.PreviewCookiesMiddleware")


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
