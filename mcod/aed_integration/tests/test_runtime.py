from unittest.mock import Mock

import pytest
from django.test import override_settings

from mcod.aed_integration.services import validate_public_api_url
from mcod.aed_integration.validation import AEDDataError
from mcod.core.api.rdf.registry import registry


@pytest.mark.parametrize("api_url", ["/api", "", "http://mcod.invalid/api"])
def test_file_publication_requires_a_canonical_https_api_url(api_url):
    with override_settings(API_URL=api_url):
        with pytest.raises(AEDDataError) as failure:
            validate_public_api_url()
    assert failure.value.code == "public_api_url_missing"


def test_canonical_https_api_url_is_accepted():
    with override_settings(API_URL="https://mcod-test.invalid/api"):
        validate_public_api_url()


def test_disabled_rdf_does_not_contact_the_external_graph_store(monkeypatch):
    update = Mock(side_effect=AssertionError("Disabled RDF must not make network requests"))
    monkeypatch.setattr(registry.sparql_store, "update", update)
    with override_settings(USE_RDF_DB=False):
        registry.process_graph("create", "resources", "Resource", -1)
    update.assert_not_called()


@pytest.mark.django_db
def test_swagger_uses_same_origin_and_includes_aed_specification():
    from mcod.aed_integration.tests.test_api import _client

    response = _client().simulate_get("/doc")
    assert response.status_code == 200
    assert "/api/spec/1.4" in response.text
    assert "/api/integrations/aed/openapi.yaml" in response.text
    assert "https://mcod-test.invalid" not in response.text
