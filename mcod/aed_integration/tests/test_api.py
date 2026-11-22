import json

import falcon.testing
import pytest
from django.test import override_settings

from mcod.aed_integration.models import AEDDatasetMapping, AEDOrganizationMapping
from mcod.categories.factories import CategoryFactory
from mcod.datasets.models import Dataset
from mcod.organizations.factories import OrganizationFactory
from mcod.resources.models import Resource, ResourceFile
from mcod.tags.factories import TagFactory


SECRET = "test-only-shared-secret"


def _client():
    from mcod.api import get_api_app

    app = get_api_app()

    def fail_on_unexpected_error(request, response, exc, params):
        raise exc

    app.add_error_handler(Exception, fail_on_unexpected_error)
    return falcon.testing.TestClient(app)


def _auth_headers():
    return {
        "Authorization": "Bearer {}".format(SECRET),
        "X-Forwarded-Proto": "https",
    }


def _csv_upload_body(fields, content):
    boundary = "----aed-puls-test-boundary"
    parts = []
    for name, value in fields.items():
        parts.append(
            (
                "--{}\r\nContent-Disposition: form-data; name=\"{}\"\r\n\r\n{}\r\n".format(
                    boundary, name, value
                )
            ).encode("utf-8")
        )
    parts.append(
        (
            "--{}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"source.csv\"\r\n"
            "Content-Type: text/csv\r\n\r\n"
        ).format(boundary).encode("utf-8")
        + content
        + b"\r\n"
    )
    parts.append("--{}--\r\n".format(boundary).encode("ascii"))
    return boundary, b"".join(parts)


def _source_csv():
    license_name = Dataset.LICENSE_CODE_TO_NAME[Dataset.LICENSE_CC0]
    return (
        "device_id,name,latitude,longitude,availability,hours,status,updated_at,"
        "responsible_institution,source_dataset_id,source_url,license,verification_status\n"
        "aed-a-1,City Hall,52.2297,21.0122,public,24/7,active,2026-11-20,"
        "Organization A,source-a,https://example.org/aed,{},source_reported\n"
    ).format(license_name).encode("utf-8")


def _mapping(external_id, organization):
    mapping = AEDOrganizationMapping.objects.create(
        external_organization_id=external_id,
        organization=organization,
        default_category=CategoryFactory.create(status="published"),
    )
    mapping.default_tags.add(TagFactory.create())
    return mapping


@pytest.mark.django_db
def test_integration_write_api_requires_secret_and_https():
    client = _client()
    with override_settings(AED_INTEGRATION_SECRET=SECRET, AED_REQUIRE_HTTPS=True):
        no_auth = client.simulate_get(
            "/integrations/aed/v1/institutions", headers={"X-Forwarded-Proto": "https"}
        )
        bad_scheme = client.simulate_get(
            "/integrations/aed/v1/institutions",
            headers={"Authorization": "Bearer {}".format(SECRET)},
        )

    assert no_auth.status_code == 401
    assert bad_scheme.status_code == 400


@pytest.mark.django_db
def test_dataset_api_scopes_assignments_to_mapped_institution():
    organization_a = OrganizationFactory.create(
        title="AED Test Organization A",
        status="published",
    )
    organization_b = OrganizationFactory.create(title="AED Test Organization B")
    _mapping("org-a", organization_a)
    _mapping("org-b", organization_b)
    client = _client()
    dataset_payload = {
        "external_dataset_id": "source-a",
        "title": "AED locations from organization A",
        "description": "Published AED source records maintained by organization A.",
        "source_url": "https://example.org/aed/source-a",
        "license": Dataset.LICENSE_CODE_TO_NAME[Dataset.LICENSE_CC0],
    }

    with override_settings(AED_INTEGRATION_SECRET=SECRET, AED_REQUIRE_HTTPS=True):
        created = client.simulate_post(
            "/integrations/aed/v1/organizations/org-a/datasets",
            json=dataset_payload,
            headers=_auth_headers(),
        )

    assert created.status_code == 201, created.text
    created_data = json.loads(created.text)
    mcod_dataset_id = created_data["dataset_id"]
    assert AEDDatasetMapping.objects.filter(
        organization_mapping__external_organization_id="org-a",
        external_dataset_id="source-a",
        dataset_id=mcod_dataset_id,
    ).exists()

    with override_settings(AED_INTEGRATION_SECRET=SECRET, AED_REQUIRE_HTTPS=True):
        published_dataset = client.simulate_post(
            "/integrations/aed/v1/organizations/org-a/datasets/source-a/publish",
            headers=_auth_headers(),
        )
        boundary, body = _csv_upload_body(
            {
                "external_dataset_id": "source-a",
                "title": "AED source from organization A",
                "description": "Record locations submitted by organization A.",
                "source_url": "https://example.org/aed/source-a",
            },
            _source_csv(),
        )
        uploaded_resource = client.simulate_post(
            "/integrations/aed/v1/organizations/org-a/datasets/source-a/resources",
            body=body,
            headers={
                **_auth_headers(),
                "Content-Type": "multipart/form-data; boundary={}".format(boundary),
            },
        )
        upload_data = json.loads(uploaded_resource.text)
        cross_org_read = client.simulate_get(
            "/integrations/aed/v1/organizations/org-b/datasets/source-a",
            headers=_auth_headers(),
        )
        cross_org_assign = client.simulate_post(
            "/integrations/aed/v1/organizations/org-b/datasets",
            json={
                **dataset_payload,
                "external_dataset_id": "foreign-source",
                "mcod_dataset_id": mcod_dataset_id,
            },
            headers=_auth_headers(),
        )

    assert published_dataset.status_code == 200, published_dataset.text
    assert uploaded_resource.status_code == 202, uploaded_resource.text
    assert upload_data["accepted_rows"] == 1
    assert upload_data["status"] == "draft"
    assert cross_org_read.status_code == 404
    assert cross_org_assign.status_code == 422
    assert not AEDDatasetMapping.objects.filter(
        organization_mapping__external_organization_id="org-b",
        external_dataset_id="foreign-source",
    ).exists()
    resource_id = upload_data["resource_id"]
    with override_settings(AED_INTEGRATION_SECRET=SECRET, AED_REQUIRE_HTTPS=True):
        pending = client.simulate_post(
            "/integrations/aed/v1/organizations/org-a/resources/{}/publish".format(resource_id),
            headers=_auth_headers(),
        )
        cross_org_resource = client.simulate_get(
            "/integrations/aed/v1/organizations/org-b/resources/{}".format(resource_id),
            headers=_auth_headers(),
        )
        resource_file = ResourceFile.objects.get(resource_id=resource_id, is_main=True)
        draft_download = client.simulate_get("/media/resources/" + resource_file.file.name)
    assert pending.status_code == 409, pending.text
    assert cross_org_resource.status_code == 404
    assert draft_download.status_code == 404
    assert Resource.objects.get(pk=resource_id).status == "draft"
