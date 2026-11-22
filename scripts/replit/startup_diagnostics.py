"""Small, dependency-free startup messages, independent of Django logging."""

import datetime
import faulthandler
import json
import os
import sys


_last_stage = "bootstrap"


def event(stage, **fields):
    global _last_stage
    if os.environ.get("MCOD_STARTUP_DIAGNOSTICS") != "1":
        return
    _last_stage = stage
    record = {
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "component": "mcod-admin-startup",
        "pid": os.getpid(),
        "stage": stage,
    }
    record.update(fields)
    # Do not use Django's loggers: production dictConfig can disable them.
    # Callers pass an explicit allowlist, never environment dumps or DB URLs.
    print(json.dumps(record, sort_keys=True), file=sys.stderr, flush=True)


def last_stage():
    return _last_stage


def arm_traceback_timer():
    if os.environ.get("MCOD_STARTUP_DIAGNOSTICS") != "1":
        return
    seconds = float(os.environ.get("MCOD_ADMIN_TRACE_SECONDS", "45"))
    if seconds <= 0:
        raise ValueError("MCOD_ADMIN_TRACE_SECONDS must be positive")
    faulthandler.enable(file=sys.stderr, all_threads=True)
    # Diagnostic only: no timeout exit, readiness gate or fabricated HTTP reply.
    # Native watchdog also reports a blocked Python import or psycopg2 connect.
    faulthandler.dump_traceback_later(
        seconds, repeat=True, file=sys.stderr, exit=False
    )
    event("startup_traceback_timer_armed", interval_seconds=seconds)


def cancel_traceback_timer():
    faulthandler.cancel_dump_traceback_later()
