"""Unique test database and namespaces; no production storage or live worker."""

from mcod.settings.aed_e2e import *  # noqa: F403,F405

REPLIT_APP_STORAGE_ENABLED = False
CELERY_BROKER_URL = "memory://"
