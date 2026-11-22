"""Pure authentication checks: no database, files, workers or HTTP requests."""

from types import SimpleNamespace

import falcon
import pytest
from django.test import override_settings

from mcod.aed_integration.views import authenticate_integration, secure


def request_with(authorization):
    headers = {"Authorization": authorization, "X-Forwarded-Proto": "https"}
    return SimpleNamespace(get_header=headers.get)


@pytest.mark.parametrize("authorization", [
    None,
    "Bearer",
    "Basic test-only-secret",
    "Bearer incorrect-test-secret",
    "Bearer błędny-token",
])
def test_invalid_bearer_is_401_without_accessing_data(authorization):
    with override_settings(AED_INTEGRATION_SECRET="test-only-secret", AED_REQUIRE_HTTPS=True):
        with pytest.raises(falcon.HTTPUnauthorized):
            authenticate_integration(request_with(authorization))


def test_matching_bearer_is_accepted():
    with override_settings(AED_INTEGRATION_SECRET="test-only-secret", AED_REQUIRE_HTTPS=True):
        authenticate_integration(request_with("Bearer test-only-secret"))


def test_secure_handler_rejects_unicode_token_before_handler_runs():
    class Probe:
        called = False

        @secure
        def on_get(self, request, response):
            self.called = True

    probe = Probe()
    response = falcon.Response()
    with override_settings(AED_INTEGRATION_SECRET="test-only-secret", AED_REQUIRE_HTTPS=True):
        probe.on_get(request_with("Bearer błędny-token"), response)
    assert not probe.called
    assert response.status == falcon.HTTP_401
    assert response.media["error"]["code"] == "integration_authentication_failed"
    assert response.get_header("Cache-Control") == "no-store"
