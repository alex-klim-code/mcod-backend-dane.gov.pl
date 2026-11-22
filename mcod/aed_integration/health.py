"""Dependency readiness for the existing MCOD integration, not a startup loop."""

import logging

from django.conf import settings
from django.core.cache import caches
from django.db import connection, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from elasticsearch_dsl.connections import connections

logger = logging.getLogger("mcod")


def database_ready():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        return cursor.fetchone() == (1,)


def sessions_ready():
    return bool(caches["sessions"].client.get_client(write=False).ping())


def search_ready():
    client = connections.get_connection()
    names = [
        settings.ELASTICSEARCH_INDEX_NAMES[name]
        for name in ("institutions", "datasets", "resources")
    ]
    result = client.search(
        index=",".join(names),
        body={"size": 0, "query": {"match_none": {}}},
        request_timeout=2, allow_no_indices=False, ignore_unavailable=False,
    )
    shards = result.get("_shards", {})
    return (
        not result.get("timed_out", True)
        and shards.get("failed") == 0
        and shards.get("successful", 0) > 0
    )


def broker_ready():
    from mcod.celeryapp import app

    with app.connection_for_write(connect_timeout=2) as broker:
        broker.ensure_connection(max_retries=0, timeout=2)
        return broker.connected


@transaction.non_atomic_requests
@require_GET
def readiness_view(request):
    """503 until database, sessions, search and task submission work.

    This does not claim that an individual uploaded file has been validated:
    the existing AED status and publish endpoints enforce that separately.
    """
    checks = {}
    for name, probe in (
        ("database", database_ready),
        ("sessions", sessions_ready),
        ("search", search_ready),
        ("broker", broker_ready),
    ):
        try:
            checks[name] = "ok" if probe() else "unavailable"
        except Exception:
            # Keep connection details and credentials out of the public response.
            checks[name] = "unavailable"
            logger.warning("AED readiness dependency unavailable: %s", name)
    ready = all(status == "ok" for status in checks.values())
    response = JsonResponse(
        {"status": "ready" if ready else "not_ready", "checks": checks},
        status=200 if ready else 503,
    )
    response["Cache-Control"] = "no-store"
    return response
