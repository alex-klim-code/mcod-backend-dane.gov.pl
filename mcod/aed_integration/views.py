import hmac
import json
import logging
from functools import wraps

import falcon
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from mcod.aed_integration.models import AEDAggregateState, AEDDatasetMapping, AEDOrganizationMapping
from mcod.aed_integration.services import (
    create_dataset,
    create_or_update_resource,
    get_dataset_mapping,
    get_mapping,
    publish_dataset,
    publish_resource,
    resource_status,
    update_dataset,
    write_audit,
)
from mcod.aed_integration.tasks import aggregate_aed_catalog_task
from mcod.aed_integration.validation import AEDDataError
from mcod.resources.models import Resource

logger = logging.getLogger("mcod")


def authenticate_integration(request):
    expected = getattr(settings, "AED_INTEGRATION_SECRET", "")
    if not expected:
        raise falcon.HTTPServiceUnavailable(
            title="AED integration is not configured",
            description="Configure AED_INTEGRATION_SECRET in Replit Secrets.",
        )
    if getattr(settings, "AED_REQUIRE_HTTPS", False):
        if request.get_header("X-Forwarded-Proto", "").lower() != "https":
            raise falcon.HTTPBadRequest(description="AED integration requests must use HTTPS.")

    authorization = request.get_header("Authorization", "")
    scheme, _, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, expected):
        raise falcon.HTTPUnauthorized(
            title="401 Unauthorized",
            description="A valid AED integration bearer token is required.",
            code="integration_authentication_failed",
        )


def secure(handler):
    @wraps(handler)
    def wrapped(self, request, response, *args, **kwargs):
        authenticate_integration(request)
        return handler(self, request, response, *args, **kwargs)

    return wrapped


def _payload(request):
    try:
        payload = request.get_media()
    except Exception:
        raise falcon.HTTPBadRequest(description="The request body is not valid JSON or multipart form data.")
    if not isinstance(payload, dict):
        raise falcon.HTTPBadRequest(description="The request body must be an object.")
    return payload


def _mapping_or_404(external_organization_id):
    mapping = get_mapping(external_organization_id)
    if not mapping:
        raise falcon.HTTPNotFound(description="No enabled MCOD institution mapping exists for this organization.")
    return mapping


def _raise_data_error(exc, action, mapping=None, dataset=None, resource=None):
    write_audit(action, "rejected", mapping=mapping, dataset=dataset, resource=resource, code=exc.code)
    if exc.code == "validation_pending":
        raise falcon.HTTPConflict(title="Validation is still running", description=str(exc), code=exc.code)
    if exc.code == "validation_failed":
        raise falcon.HTTPUnprocessableEntity(title="MCOD validation failed", description=str(exc), code=exc.code)
    raise falcon.HTTPUnprocessableEntity(title="Invalid AED integration request", description=str(exc), code=exc.code)


class AEDInstitutionsView:
    @secure
    def on_get(self, request, response):
        mappings = AEDOrganizationMapping.objects.filter(enabled=True).select_related("organization")
        response.media = {
            "data": [
                {
                    "external_organization_id": item.external_organization_id,
                    "mcod_institution_id": item.organization_id,
                    "name": item.organization.title,
                    "status": item.organization.status,
                    "mcod_api_url": "/api/institutions/{}".format(item.organization_id),
                }
                for item in mappings
            ]
        }


class AEDDatasetsView:
    @secure
    def on_post(self, request, response, external_organization_id):
        mapping = _mapping_or_404(external_organization_id)
        payload = _payload(request)
        try:
            dataset_mapping, created = create_dataset(mapping, payload)
        except AEDDataError as exc:
            _raise_data_error(exc, "dataset_create", mapping)
        write_audit(
            "dataset_created" if created else "dataset_reused",
            "success",
            mapping=mapping,
            dataset=dataset_mapping.dataset,
        )
        response.status = falcon.HTTP_201 if created else falcon.HTTP_200
        response.media = {
            "external_dataset_id": dataset_mapping.external_dataset_id,
            "dataset_id": dataset_mapping.dataset_id,
            "status": dataset_mapping.dataset.status,
            "metadata_url": "/api/datasets/{}".format(dataset_mapping.dataset_id),
        }


class AEDDatasetView:
    @secure
    def on_get(self, request, response, external_organization_id, external_dataset_id):
        mapping = _mapping_or_404(external_organization_id)
        dataset_mapping = get_dataset_mapping(mapping, external_dataset_id)
        if not dataset_mapping:
            raise falcon.HTTPNotFound
        dataset = dataset_mapping.dataset
        resources = Resource.objects.filter(dataset_id=dataset.pk).order_by("pk")
        response.media = {
            "external_dataset_id": dataset_mapping.external_dataset_id,
            "dataset_id": dataset.pk,
            "title": dataset.title,
            "status": dataset.status,
            "resources": [
                {
                    "resource_id": item.pk,
                    "status": item.status,
                    "metadata_url": "/api/resources/{}".format(item.pk) if item.is_published else None,
                    "file_url": "/api/resources/{}/file".format(item.pk) if item.is_published else None,
                }
                for item in resources
            ],
        }

    @secure
    def on_patch(self, request, response, external_organization_id, external_dataset_id):
        mapping = _mapping_or_404(external_organization_id)
        try:
            dataset_mapping = update_dataset(mapping, external_dataset_id, _payload(request))
        except AEDDataError as exc:
            _raise_data_error(exc, "dataset_update", mapping)
        if not dataset_mapping:
            raise falcon.HTTPNotFound
        write_audit("dataset_updated", "success", mapping=mapping, dataset=dataset_mapping.dataset)
        response.media = {
            "external_dataset_id": external_dataset_id,
            "dataset_id": dataset_mapping.dataset_id,
            "status": dataset_mapping.dataset.status,
            "metadata_url": "/api/datasets/{}".format(dataset_mapping.dataset_id),
        }


class AEDDatasetPublishView:
    @secure
    def on_post(self, request, response, external_organization_id, external_dataset_id):
        mapping = _mapping_or_404(external_organization_id)
        try:
            dataset = publish_dataset(mapping, external_dataset_id)
        except AEDDataError as exc:
            _raise_data_error(exc, "dataset_publish", mapping)
        if not dataset:
            raise falcon.HTTPNotFound
        response.media = {
            "dataset_id": dataset.pk,
            "status": dataset.status,
            "metadata_url": "/api/datasets/{}".format(dataset.pk),
        }


class AEDDatasetResourcesView:
    @secure
    def on_post(self, request, response, external_organization_id, external_dataset_id):
        mapping = _mapping_or_404(external_organization_id)
        payload = _payload(request)
        upload = payload.get("file")
        title = str(payload.get("title", "")).strip()
        description = str(payload.get("description", "")).strip()
        source_url = str(payload.get("source_url", "")).strip()
        try:
            resource, row_count = create_or_update_resource(
                mapping,
                external_dataset_id,
                upload,
                title,
                description,
                source_url,
            )
        except AEDDataError as exc:
            _raise_data_error(exc, "resource_upload", mapping)
        response.status = falcon.HTTP_202
        response.media = dict(resource_status(resource), accepted_rows=row_count)


class AEDResourceView:
    @secure
    def on_get(self, request, response, external_organization_id, resource_id):
        mapping = _mapping_or_404(external_organization_id)
        try:
            resource = Resource.objects.select_related("dataset").get(
                pk=resource_id,
                dataset__organization_id=mapping.organization_id,
                dataset__aed_integration_mapping__organization_mapping=mapping,
            )
        except Resource.DoesNotExist:
            raise falcon.HTTPNotFound
        response.media = resource_status(resource)

    @secure
    def on_put(self, request, response, external_organization_id, resource_id):
        mapping = _mapping_or_404(external_organization_id)
        payload = _payload(request)
        upload = payload.get("file")
        try:
            resource, row_count = create_or_update_resource(
                mapping,
                payload.get("external_dataset_id", ""),
                upload,
                str(payload.get("title", "")).strip(),
                str(payload.get("description", "")).strip(),
                str(payload.get("source_url", "")).strip(),
                resource_id=resource_id,
            )
        except AEDDataError as exc:
            _raise_data_error(exc, "resource_update", mapping)
        if not resource:
            raise falcon.HTTPNotFound
        response.status = falcon.HTTP_202
        response.media = dict(resource_status(resource), accepted_rows=row_count)


class AEDResourcePublishView:
    @secure
    def on_post(self, request, response, external_organization_id, resource_id):
        mapping = _mapping_or_404(external_organization_id)
        try:
            resource = publish_resource(mapping, resource_id)
        except AEDDataError as exc:
            _raise_data_error(exc, "resource_publish", mapping)
        if not resource:
            raise falcon.HTTPNotFound
        response.media = resource_status(resource)


class AEDAggregateView:
    @secure
    def on_get(self, request, response):
        state = AEDAggregateState.objects.select_related("dataset", "published_resource").filter(singleton=True).first()
        if not state:
            response.media = {"status": AEDAggregateState.STATUS_IDLE, "record_count": 0}
            return
        response.media = {
            "status": state.status,
            "record_count": state.record_count,
            "last_run_at": state.last_run_at.isoformat() if state.last_run_at else None,
            "last_error": state.last_error or None,
            "dataset_id": state.dataset_id,
            "resource_id": state.published_resource_id,
            "metadata_url": (
                "/api/resources/{}".format(state.published_resource_id) if state.published_resource_id else None
            ),
            "file_url": (
                "/api/resources/{}/file".format(state.published_resource_id)
                if state.published_resource_id
                else None
            ),
        }

    @secure
    def on_post(self, request, response):
        state, _created = AEDAggregateState.objects.get_or_create(singleton=True)
        if not state.owner_mapping_id:
            raise falcon.HTTPConflict(
                title="Aggregate owner is not configured",
                description="Select an enabled MCOD institution mapping in Django admin first.",
            )
        state.status = AEDAggregateState.STATUS_QUEUED
        state.last_error = ""
        state.last_run_at = timezone.now()
        state.save(update_fields=("status", "last_error", "last_run_at", "updated_at"))
        try:
            task = aggregate_aed_catalog_task.delay()
        except Exception as exc:
            state.mark_failed("queue_unavailable")
            logger.error("Unable to queue AED aggregate task (%s).", type(exc).__name__)
            raise falcon.HTTPServiceUnavailable(
                title="Aggregation is unavailable",
                description="The MCOD background worker could not accept the request.",
            )
        response.status = falcon.HTTP_202
        response.media = {"status": AEDAggregateState.STATUS_QUEUED, "task_id": task.id}
