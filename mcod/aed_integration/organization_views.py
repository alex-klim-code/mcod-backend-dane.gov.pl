"""AED-only routes. The public MCOD institutions catalog remains unchanged."""

import falcon
from django.core.exceptions import ValidationError

from mcod.aed_integration.forms import AEDInstitutionForm
from mcod.aed_integration.institutions import (
    institution_data, permissions, request_data, save_institution, submit_request,
)
from mcod.aed_integration.models import AEDOrganizationMapping, AEDOrganizationRequest
from mcod.aed_integration.validation import AEDDataError, REQUIRED_COLUMNS
from mcod.aed_integration.views import _mapping_or_404, _payload, _raise_data_error, secure
from mcod.datasets.models import Dataset


class AEDOrganizationRequestsView:
    @secure
    def on_post(self, request, response):
        try:
            item, created = submit_request(_payload(request))
        except AEDDataError as exc:
            _raise_data_error(exc, "organization_request")
        except ValidationError:
            raise falcon.HTTPUnprocessableEntity(description="The request failed native model validation.")
        response.status = falcon.HTTP_201 if created else falcon.HTTP_200
        response.media = request_data(item)


class AEDOrganizationRequestView:
    @secure
    def on_get(self, request, response, external_organization_id):
        item = AEDOrganizationRequest.objects.filter(external_organization_id=external_organization_id).first()
        mapping = AEDOrganizationMapping.objects.filter(external_organization_id=external_organization_id).first()
        if not item and not mapping:
            raise falcon.HTTPNotFound
        response.media = request_data(item) if item else {"external_organization_id": external_organization_id}
        if mapping:
            response.media.update({
                "status": "approved" if mapping.enabled else "suspended",
                "mcod_institution_id": mapping.organization_id,
                "permissions": permissions(mapping) if mapping.enabled else {},
            })


class AEDOrganizationInstitutionView:
    @secure
    def on_get(self, request, response, external_organization_id):
        mapping = _mapping_or_404(external_organization_id)
        response.media = {"data": institution_data(mapping.organization), "permissions": permissions(mapping)}

    @secure
    def on_post(self, request, response, external_organization_id):
        try:
            organization = save_institution(external_organization_id, _payload(request))
        except AEDDataError as exc:
            _raise_data_error(exc, "institution_create")
        response.status = falcon.HTTP_201
        response.media = {"data": institution_data(organization)}

    @secure
    def on_patch(self, request, response, external_organization_id):
        mapping = _mapping_or_404(external_organization_id)
        try:
            organization = save_institution(external_organization_id, _payload(request), mapping=mapping)
        except AEDDataError as exc:
            _raise_data_error(exc, "institution_update", mapping)
        response.media = {"data": institution_data(organization)}


class AEDSchemasView:
    @secure
    def on_get(self, request, response):
        from mcod.aed_integration.contracts import DATASET_FLAGS
        from mcod.datasets.forms import UPDATE_FREQUENCY_FOR_CREATE
        fields = {}
        for name, field in AEDInstitutionForm().fields.items():
            value = {"type": "string", "required": field.required}
            if getattr(field, "max_length", None):
                value["max_length"] = field.max_length
            if getattr(field, "choices", None):
                value["enum"] = [key for key, _label in field.choices]
            fields[name] = value
        response.media = {
            "institution": fields,
            "licenses": [str(label) for _key, label in Dataset.LICENSES],
            "dataset_boolean_fields": list(DATASET_FLAGS),
            "dataset_update_frequencies": [key for key, _label in UPDATE_FREQUENCY_FOR_CREATE if key],
            "aed_required_columns": list(REQUIRED_COLUMNS),
            "institution_catalog": "/api/institutions",
            "institution_details": "/api/institutions/{id}",
            "institution_datasets": "/api/institutions/{id}/datasets",
        }
