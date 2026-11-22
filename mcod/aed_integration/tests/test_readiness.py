"""Unit coverage for readiness reporting; live probes are checked separately."""

import pytest
from django.test import RequestFactory

from mcod.aed_integration import health


PROBES = ("database_ready", "sessions_ready", "search_ready", "broker_ready")


def configure_probes(monkeypatch):
    for name in PROBES:
        monkeypatch.setattr(health, name, lambda: True)


def test_ready_response_is_not_cached(monkeypatch):
    configure_probes(monkeypatch)
    response = health.readiness_view(RequestFactory().get("/health/ready/"))
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize("probe", PROBES)
@pytest.mark.parametrize("raises", (False, True))
def test_missing_dependency_returns_503_without_details(monkeypatch, probe, raises):
    configure_probes(monkeypatch)

    def unavailable():
        if raises:
            raise RuntimeError("private-connection-details")
        return False

    monkeypatch.setattr(health, probe, unavailable)
    response = health.readiness_view(RequestFactory().get("/health/ready/"))
    assert response.status_code == 503
    assert b"unavailable" in response.content
    assert b"private-connection-details" not in response.content
