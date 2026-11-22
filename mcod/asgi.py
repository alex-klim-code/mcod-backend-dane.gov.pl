import logging
import os

# Only the Replit admin launcher enables this; no logging/import changes for
# other MCOD entrypoints. Writes directly to stderr, not Django's dictConfig.
def _startup_stage(name):
    if os.environ.get("MCOD_STARTUP_DIAGNOSTICS") == "1":
        from scripts.replit.startup_diagnostics import event

        event(name)


_startup_stage("asgi_module_enter")

import django
_startup_stage("django_import_complete")
import environ
from channels.routing import get_default_application

log = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mcod.settings")
os.environ.setdefault("COMPONENT", "admin")

env = environ.Env()
ROOT_DIR = environ.Path(__file__) - 1

try:
    env.read_env(ROOT_DIR.file(".env"))
except FileNotFoundError:
    pass

DEBUG = True if env("DEBUG", default="no") in ("yes", 1, "true") else False
DEBUGGER = env("DEBUGGER", default=None)

_startup_stage("django_setup_begin")
django.setup()
_startup_stage("django_setup_complete")

if DEBUG and DEBUGGER == "debugpy":
    import debugpy

    try:
        debugpy.listen(("0.0.0.0", 5678))
        log.info("Debugger attached.")
    except Exception:
        log.info("Debugger is already running.")

_startup_stage("asgi_routing_import_begin")
application = get_default_application()
_startup_stage("asgi_routing_import_complete")

log.info("App started successfully.")
