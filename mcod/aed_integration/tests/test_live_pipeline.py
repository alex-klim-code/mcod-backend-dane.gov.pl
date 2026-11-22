"""Opt-in: real Celery worker, validators, PostgreSQL, Elasticsearch and App Storage."""

import csv
import io
import os
import time
from urllib.parse import urlsplit

import pytest
from celery.contrib.testing.worker import start_worker
from django.conf import settings
from django.test import override_settings
from django_elasticsearch_dsl.registries import registry
from elasticsearch_dsl.connections import connections

from mcod.aed_integration.models import AEDAggregateState
from mcod.aed_integration.tests.test_api import _auth_headers, _client, _csv_upload_body, _mapping
from mcod.aed_integration.tests.test_validation import csv_bytes, make_csv_row
from mcod.celeryapp import app as celery_app
from mcod.core.storages import ResourcesStorage
from mcod.datasets.models import Dataset
from mcod.organizations.factories import OrganizationFactory
from mcod.organizations.models import Organization
from mcod.resources.models import Resource, ResourceFile
from mcod.users.factories import EditorFactory


pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(os.environ.get("RUN_AED_E2E") != "1", reason="Opt-in real service E2E test"),
]


def wait_for(check, description, seconds=120):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        last = check()
        if last:
            return last
        time.sleep(1)
    raise AssertionError("Timed out waiting for {}. Last result: {!r}".format(description, last))


def test_real_aed_publication_and_aggregate(monkeypatch, admin_client):
    assert settings.REPLIT_APP_STORAGE_ENABLED
    broker_url = celery_app.conf.broker_url
    if os.environ.get("AED_E2E_BROKER_URL"):
        assert urlsplit(broker_url).path.startswith("/aed-e2e-")
    else:
        assert broker_url == "memory://"
    assert all(name.startswith("aed-e2e-") for name in settings.ELASTICSEARCH_INDEX_NAMES.values())
    uploaded_names = set()
    original_save = ResourcesStorage._save

    def tracked_save(storage, name, content):
        result = original_save(storage, name, content)
        uploaded_names.add(result)
        return result

    monkeypatch.setattr(ResourcesStorage, "_save", tracked_save)
    indexes = list(registry.get_indices())
    for index in indexes:
        if not index.exists():
            index.create()

    def request_ok(method, path, **kwargs):
        response = getattr(client, "simulate_" + method)(
            path, headers={**_auth_headers(), **kwargs.pop("headers", {})}, **kwargs
        )
        assert response.status_code in (200, 201, 202), response.text
        return response.json

    def validated(resource_id):
        resource = Resource.objects.get(pk=resource_id)
        statuses = (
            resource.file_tasks_last_status,
            resource.data_tasks_last_status,
            resource.link_tasks_last_status,
        )
        if "FAILURE" in statuses:
            failures = list(resource.file_tasks.values("status", "result"))
            failures += list(resource.data_tasks.values("status", "result"))
            raise AssertionError("Real validation failed: {!r}; {!r}".format(statuses, failures))
        return resource if statuses == ("SUCCESS", "SUCCESS", "SUCCESS") else None

    def published_aggregate():
        state = AEDAggregateState.objects.get(singleton=True)
        if state.status == "failed":
            resource = state.pending_resource
            failures = [] if not resource else (
                list(resource.file_tasks.values("status", "result"))
                + list(resource.data_tasks.values("status", "result"))
            )
            raise AssertionError("Aggregate failed: {}; {!r}".format(state.last_error, failures))
        if state.status == "published" and state.record_count == 5:
            return state
        return None

    try:
        client = _client()
        with override_settings(
            AED_INTEGRATION_SECRET="test-only-shared-secret", AED_REQUIRE_HTTPS=True
        ):
            mapping_a = _mapping(
                "live-org-a",
                OrganizationFactory.create(
                    title="Isolated E2E A", institution_type="state", status="published", image=""
                ),
            )
            _mapping(
                "live-org-b",
                OrganizationFactory.create(
                    title="Isolated E2E B", institution_type="state", status="published", image=""
                ),
            )
            # Real MCOD records, identity and API authorization in the isolated
            # PostgreSQL database. No new institution-write API is invented.
            assert mapping_a.organization.pk
            assert client.simulate_post(
                "/institutions", json={"title": "Not a supported write API"}
            ).status_code == 405
            institutions = request_ok("get", "/integrations/aed/v1/institutions")
            assert len(institutions["data"]) == 2
            password = "Isolated-only-password-82!"
            institution_user = EditorFactory.create(
                email="isolated-aed-editor@example.org",
                password=password, organizations=[mapping_a.organization],
            )
            login = client.simulate_post("/auth/login", json={
                "data": {"type": "user", "attributes": {
                    "email": institution_user.email, "password": password,
                }},
            })
            assert login.status_code in (200, 201), login.status_code
            assert int(login.json["data"]["id"]) == institution_user.pk
            assert institution_user.organizations.filter(pk=mapping_a.organization_id).exists()
            AEDAggregateState.objects.create(owner_mapping=mapping_a, license_chosen=Dataset.LICENSE_CC0)
            source_rows = {}
            resources = {}
            with start_worker(
                celery_app, pool="solo", concurrency=1, perform_ping_check=False,
                loglevel="WARNING", shutdown_timeout=30,
            ):
                for org, count in (("a", 3), ("b", 2)):
                    dataset_id = "live-source-" + org
                    prefix = "/integrations/aed/v1/organizations/live-org-" + org
                    request_ok("post", prefix + "/datasets", json={
                        "external_dataset_id": dataset_id,
                        "title": "Isolated AED source " + org,
                        "description": "Isolated E2E source records for actual MCOD validation.",
                        "source_url": "https://example.org/" + dataset_id,
                        "license": Dataset.LICENSE_CODE_TO_NAME[Dataset.LICENSE_CC0],
                    })
                    request_ok("post", prefix + "/datasets/" + dataset_id + "/publish")
                    source_rows[org] = [
                        make_csv_row(
                            device_id="live-{}-{}".format(org, number),
                            name="AED {} {}".format(org, number),
                            source_dataset_id=dataset_id,
                            latitude=str(52.0 + number / 100),
                            longitude=str(21.0 + (ord(org) - ord("a")) / 10),
                        )
                        for number in range(count)
                    ]
                    boundary, body = _csv_upload_body(
                        {"title": "Live AED source " + org}, csv_bytes(source_rows[org])
                    )
                    response = request_ok(
                        "post", prefix + "/datasets/" + dataset_id + "/resources",
                        body=body,
                        headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
                    )
                    resources[org] = response["resource_id"]
                    wait_for(lambda: validated(resources[org]), "real source validation " + org)
                    stored_file = ResourceFile.objects.get(resource_id=resources[org], is_main=True).file
                    cached_path = stored_file.path
                    os.unlink(cached_path)
                    with open(stored_file.path, "rb") as restored:
                        assert restored.read() == csv_bytes(source_rows[org])
                    request_ok("post", prefix + "/resources/{}/publish".format(resources[org]))

                state = wait_for(published_aggregate, "real 5-record aggregate", seconds=180)
                old_resource_id = state.published_resource_id
                source_rows["a"][0]["name"] = "Changed by real E2E"
                source_rows["a"][0]["updated_at"] = "2026-11-22T00:00:00Z"
                boundary, body = _csv_upload_body(
                    {"title": "Updated live AED", "external_dataset_id": "live-source-a"},
                    csv_bytes(source_rows["a"]),
                )
                request_ok(
                    "put",
                    "/integrations/aed/v1/organizations/live-org-a/resources/{}".format(resources["a"]),
                    body=body,
                    headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
                )
                wait_for(lambda: validated(resources["a"]), "updated source validation")
                request_ok(
                    "post",
                    "/integrations/aed/v1/organizations/live-org-a/resources/{}/publish".format(resources["a"]),
                )

                def updated_aggregate():
                    result = published_aggregate()
                    return result if result and result.published_resource_id != old_resource_id else None

                updated = wait_for(updated_aggregate, "updated real aggregate", seconds=180)

                def public_metadata():
                    result = client.simulate_get("/resources/{}".format(updated.published_resource_id))
                    return result if result.status_code == 200 else None

                metadata = wait_for(public_metadata, "original public MCOD resource metadata")
                assert int(metadata.json["data"]["id"]) == updated.published_resource_id
                download = client.simulate_get("/resources/{}/file".format(updated.published_resource_id))
                assert download.status_code in (301, 302, 303, 307), download.text
                path = urlsplit(download.headers["location"]).path
                if path.startswith("/api/"):
                    path = path[4:]
                contents = client.simulate_get(path)
                assert contents.status_code == 200, contents.text
                rows = list(csv.DictReader(io.StringIO(contents.content.decode("utf-8-sig"))))
                assert len(rows) == 5
                assert any(row["name"] == "Changed by real E2E" for row in rows)
                assert Resource.objects.get(pk=old_resource_id).status == "draft"
                old_file = ResourceFile.objects.get(resource_id=old_resource_id, is_main=True).file
                assert client.simulate_get("/media/resources/" + old_file.name).status_code == 404
                assert client.simulate_get(
                    "/integrations/aed/v1/institutions",
                    headers={"X-Forwarded-Proto": "https"},
                ).status_code == 401
                out_of_scope = client.simulate_get(
                    "/integrations/aed/v1/organizations/live-org-b/resources/{}".format(resources["a"]),
                    headers=_auth_headers(),
                )
                assert out_of_scope.status_code == 404
                boundary, forbidden_body = _csv_upload_body(
                    {"title": "Forbidden cross-institution update", "external_dataset_id": "live-source-b"},
                    csv_bytes(source_rows["b"]),
                )
                forbidden = client.simulate_put(
                    "/integrations/aed/v1/organizations/live-org-b/resources/{}".format(resources["a"]),
                    headers={
                        **_auth_headers(),
                        "Content-Type": "multipart/form-data; boundary=" + boundary,
                    },
                    body=forbidden_body,
                )
                assert forbidden.status_code == 404
                assert Resource.objects.get(pk=resources["a"]).title == "Updated live AED"
                # This staff session exists only in the isolated test database.
                # It is not the service identity used by the integration API.
                admin_page = admin_client.get("/resources/resource/", secure=True)
                assert admin_page.status_code == 200
                assert updated.published_resource.title.encode("utf-8") in admin_page.content
                for resource_id in (resources["a"], resources["b"], updated.published_resource_id):
                    assert "/resources/resource/{}/change/".format(resource_id).encode() in admin_page.content
                print("E2E passed: 3+2 sources, real validators, published aggregate, update, API download, auth scope.")
    finally:
        storage = ResourcesStorage()
        for name in uploaded_names:
            storage.delete(name)
        for index in indexes:
            if index._name.startswith("aed-e2e-"):
                index.delete(ignore=404)
        connections.get_connection().indices.delete(
            index=settings.ELASTICSEARCH_INDEX_PREFIX + "*", ignore=[404]
        )


def test_real_institution_creation_uses_authorized_mcod_admin(admin_client):
    path = "/organizations/organization/add/"
    page = admin_client.get(path, secure=True)
    assert page.status_code == 200
    data = {
        "title": "Isolated HTTP institution",
        "institution_type": "state",
        "status": "published",
        "postal_code": "00-001",
        "city": "Warszawa",
        "street_type": "ul.",
        "street": "Testowa",
        "street_number": "1",
        "email": "isolated-institution@example.org",
        "tel": "221234567",
        "regon": "123456785",
        "_save": "Save",
    }
    for inline in page.context["inline_admin_formsets"]:
        prefix = inline.formset.prefix
        data.update({
            prefix + "-TOTAL_FORMS": "0",
            prefix + "-INITIAL_FORMS": "0",
            prefix + "-MIN_NUM_FORMS": "0",
            prefix + "-MAX_NUM_FORMS": "1000",
        })
    created = admin_client.post(path, data, secure=True)
    errors = (
        created.context["adminform"].form.errors
        if created.status_code == 200 else {}
    )
    assert created.status_code == 302, errors
    institution = Organization.objects.get(title=data["title"])
    assert institution.status == "published"
    assert institution.created_by_id is not None
