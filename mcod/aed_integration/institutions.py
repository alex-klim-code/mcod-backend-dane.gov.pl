"""Approval and institution operations, confined to the AED integration layer."""

from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from django.utils import timezone

from mcod.aed_integration.forms import AEDInstitutionForm, INSTITUTION_FIELDS
from mcod.aed_integration.models import AEDOrganizationMapping, AEDOrganizationRequest
from mcod.aed_integration.services import write_audit
from mcod.aed_integration.validation import AEDDataError
from mcod.organizations.models import Organization


def permissions(mapping):
    return {
        "manage_institution": mapping.can_manage_institution,
        "adopt_existing_datasets": mapping.can_adopt_datasets,
        "manage_integration_datasets": mapping.enabled,
    }


def institution_data(organization):
    return dict(
        model_to_dict(organization, fields=INSTITUTION_FIELDS),
        id=organization.pk,
        metadata_url="/api/institutions/{}".format(organization.pk),
    )


def request_data(item):
    return {
        "external_organization_id": item.external_organization_id,
        "organization_name": item.organization_name,
        "request_type": item.request_type,
        "mcod_institution_id": item.organization_id,
        "status": item.status,
        "review_note": item.review_note,
        "permissions": {
            "manage_institution": item.can_manage_institution if item.status == "approved" else False,
            "adopt_existing_datasets": item.can_adopt_datasets if item.status == "approved" else False,
            "create_institution": item.status == "approved" and item.request_type == "create",
        },
    }


def submit_request(payload):
    allowed = {"external_organization_id", "organization_name", "request_type", "mcod_institution_id"}
    if set(payload) - allowed:
        raise AEDDataError("Unknown or staff-only fields in the link request.", "invalid_request_fields")
    external_id = payload.get("external_organization_id")
    name = payload.get("organization_name")
    if not isinstance(external_id, str) or not external_id.strip() or len(external_id) > 128:
        raise AEDDataError("external_organization_id must contain 1–128 characters.", "invalid_organization_id")
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise AEDDataError("organization_name must contain 1–200 characters.", "invalid_organization_name")
    external_id = external_id.strip()
    kind = payload.get("request_type")
    if kind not in ("link", "create"):
        raise AEDDataError("request_type must be link or create.", "invalid_request_type")
    target = payload.get("mcod_institution_id")
    if kind == "link":
        if type(target) is not int or not Organization.objects.filter(pk=target, status="published").exists():
            raise AEDDataError("Select an existing published institution.", "institution_not_found")
    elif target is not None:
        raise AEDDataError("A creation request must not select an existing institution.", "invalid_request")
    with transaction.atomic():
        # Serialize retries as well as competing organization registrations.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [927235, 1])
        if AEDOrganizationMapping.objects.filter(external_organization_id=external_id).exists():
            raise AEDDataError("This organization already has an administrator-managed mapping.", "mapping_exists")
        existing = AEDOrganizationRequest.objects.filter(external_organization_id=external_id).first()
        if existing:
            if existing.request_type == kind and existing.organization_id == target and existing.organization_name == name.strip():
                return existing, False
            raise AEDDataError("A different request already exists; contact the MCOD reviewer.", "request_exists")
        item = AEDOrganizationRequest(
            external_organization_id=external_id, organization_name=name.strip(),
            request_type=kind, organization_id=target,
        )
        item.full_clean()
        item.save()
        write_audit("organization_request_submitted", "accepted", external_organization_id=external_id)
        return item, True


def review_request(pk, approve, reviewer):
    if not reviewer.is_active or not reviewer.has_perm("aed_integration.change_aedorganizationrequest"):
        raise PermissionDenied
    with transaction.atomic():
        item = AEDOrganizationRequest.objects.select_for_update().get(pk=pk)
        if item.status != "pending":
            raise ValidationError("Only pending requests may be reviewed.")
        if approve:
            if not item.default_category_id or not item.default_tags.exists():
                raise ValidationError("Select a default category and at least one tag before approving.")
            if AEDOrganizationMapping.objects.filter(external_organization_id=item.external_organization_id).exists():
                raise ValidationError("A mapping already exists; manage it explicitly instead of overwriting it.")
            if item.request_type == "link":
                if not Organization.objects.filter(pk=item.organization_id, status="published").exists():
                    raise ValidationError("The selected institution is no longer published.")
                mapping = AEDOrganizationMapping(
                    external_organization_id=item.external_organization_id,
                    organization_id=item.organization_id, default_category_id=item.default_category_id,
                    can_manage_institution=item.can_manage_institution,
                    can_adopt_datasets=item.can_adopt_datasets,
                )
                mapping.full_clean()
                mapping.save()
                mapping.default_tags.set(item.default_tags.all())
        item.status = "approved" if approve else "rejected"
        item.reviewed_by = reviewer
        item.reviewed_at = timezone.now()
        item.save()
        write_audit(
            "organization_request_reviewed", item.status,
            external_organization_id=item.external_organization_id,
            details={"reviewer_id": reviewer.pk},
        )
        return item


def save_institution(external_id, payload, mapping=None):
    if set(payload) - set(INSTITUTION_FIELDS):
        raise AEDDataError("Unknown or protected institution fields.", "invalid_institution_fields")
    if any(value is not None and not isinstance(value, str) for value in payload.values()):
        raise AEDDataError("Institution fields must be strings or null where optional.", "institution_validation")
    if mapping and not mapping.can_manage_institution:
        raise PermissionDenied
    with transaction.atomic():
        # The native institution model has no unique REGON constraint. Serialize
        # integration creation to make duplicate checks effective across requests.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [927235, 1])
        grant = None
        if mapping:
            organization = Organization.objects.select_for_update().get(pk=mapping.organization_id)
            if organization.status == "published" and payload.get("status") == "draft":
                raise AEDDataError(
                    "The integration cannot unpublish an institution and its unrelated datasets.",
                    "institution_unpublish_forbidden",
                )
            values = model_to_dict(organization, fields=INSTITUTION_FIELDS)
            values.update(payload)
        else:
            grant = AEDOrganizationRequest.objects.select_for_update().filter(
                external_organization_id=external_id, request_type="create", status="approved",
            ).first()
            if not grant:
                raise PermissionDenied
            if AEDOrganizationMapping.objects.filter(external_organization_id=external_id).exists():
                raise AEDDataError("The institution has already been created. Use GET or PATCH.", "mapping_exists")
            organization = Organization()
            values = payload
        form = AEDInstitutionForm(data=values, instance=organization)
        if not form.is_valid():
            raise AEDDataError(
                "The institution failed native MCOD form validation.", "institution_validation",
                field_errors=form.errors.get_json_data(),
            )
        candidate = forms.ModelForm.save(form, commit=False)
        duplicates = Organization.raw.filter(
            Q(regon=candidate.regon) | Q(title__iexact=candidate.title, city__iexact=candidate.city)
        ).exclude(pk=candidate.pk)
        if duplicates.exists():
            raise AEDDataError("An institution with this REGON or name/city already exists; request a link.", "institution_exists")
        # Native ModelForm _post_clean has run native field/model validation.
        # Calling the base save avoids OrganizationForm's unrelated users.set().
        candidate.save()
        if grant:
            mapping = AEDOrganizationMapping.objects.create(
                external_organization_id=external_id, organization=candidate,
                default_category=grant.default_category,
                can_manage_institution=grant.can_manage_institution,
                can_adopt_datasets=grant.can_adopt_datasets,
            )
            mapping.default_tags.set(grant.default_tags.all())
        write_audit(
            "institution_created" if grant else "institution_updated", "success", mapping=mapping,
            details={"institution_id": candidate.pk, "changed_fields": sorted(payload)},
        )
        return candidate
