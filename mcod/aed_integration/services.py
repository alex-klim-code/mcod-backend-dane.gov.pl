import hashlib
import logging
import re
import unicodedata
from collections import defaultdict
from datetime import date
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from mcod.aed_integration.models import (
    AEDAggregateState,
    AEDDatasetMapping,
    AEDIntegrationAudit,
    AEDOrganizationMapping,
)
from mcod.aed_integration.validation import AEDDataError, validate_aed_file, write_csv
from mcod.datasets.models import Dataset
from mcod.resources.dga_utils import (
    FailedValidationException,
    PendingValidationException,
    check_all_resource_validations_status,
)
from mcod.resources.models import Resource, ResourceFile
from mcod.resources.tasks import entrypoint_process_resource_file_validation_task

logger = logging.getLogger("mcod")

DATASET_TITLE = "Ogólnopolski wykaz lokalizacji AED"
DATASET_NOTES = (
    "Zbiorczy wykaz lokalizacji automatycznych defibrylatorów zewnętrznych (AED). "
    "Dane zachowują źródła, licencje i deklarowany status weryfikacji poszczególnych rekordów."
)
AGGREGATE_COLUMNS = (
    "device_id",
    "name",
    "description",
    "latitude",
    "longitude",
    "address",
    "city",
    "availability",
    "hours",
    "status",
    "updated_at",
    "responsible_institution",
    "source_dataset_id",
    "source_resource_id",
    "source_mcod_dataset_id",
    "source_mcod_resource_id",
    "source_mcod_institution_id",
    "source_mcod_institution",
    "source_url",
    "license",
    "verification_status",
    "verification_evidence_url",
    "potential_duplicate",
    "duplicate_group",
)


def write_audit(action, outcome, mapping=None, dataset=None, resource=None, code=""):
    external_org_id = mapping.external_organization_id if mapping else ""
    external_dataset_id = ""
    if dataset is not None:
        external_mapping = getattr(dataset, "aed_integration_mapping", None)
        if external_mapping:
            external_dataset_id = external_mapping.external_dataset_id
    AEDIntegrationAudit.objects.create(
        action=action,
        outcome=outcome,
        code=code[:64],
        external_organization_id=external_org_id,
        external_dataset_id=external_dataset_id,
        dataset_id=dataset.pk if dataset else None,
        resource_id=resource.pk if resource else None,
    )
    logger.info(
        "AED integration action=%s outcome=%s code=%s organization=%s dataset=%s resource=%s",
        action,
        outcome,
        code or "-",
        external_org_id or "-",
        dataset.pk if dataset else "-",
        resource.pk if resource else "-",
    )


def get_mapping(external_organization_id):
    try:
        return AEDOrganizationMapping.objects.select_related(
            "organization", "default_category"
        ).get(external_organization_id=external_organization_id, enabled=True)
    except AEDOrganizationMapping.DoesNotExist:
        return None


def _license_id(name):
    for license_id, label in Dataset.LICENSES:
        if label == name:
            return license_id
    raise AEDDataError("The license is not recognized by MCOD.", "unsupported_license")


def _validate_mapping_defaults(mapping):
    if not mapping.default_category_id:
        raise AEDDataError(
            "The mapped institution needs an MCOD default category configured by an administrator.",
            "mapping_incomplete",
        )
    if not mapping.default_tags.exists():
        raise AEDDataError(
            "The mapped institution needs at least one MCOD default tag configured by an administrator.",
            "mapping_incomplete",
        )


def create_dataset(mapping, payload):
    external_dataset_id = str(payload.get("external_dataset_id", "")).strip()
    title = str(payload.get("title", "")).strip()
    notes = str(payload.get("description", "")).strip()
    source_url = str(payload.get("source_url", "")).strip()
    license_name = str(payload.get("license", "")).strip()
    if not external_dataset_id or len(external_dataset_id) > 128:
        raise AEDDataError("external_dataset_id is required and must be at most 128 characters.", "invalid_dataset_id")
    if not title or len(title) > 300:
        raise AEDDataError("title is required and must be at most 300 characters.", "invalid_title")
    if len(notes) < 20:
        raise AEDDataError("description must contain at least 20 characters.", "invalid_description")
    if not source_url.startswith("https://"):
        raise AEDDataError("source_url must use HTTPS.", "invalid_source_url")
    license_id = _license_id(license_name)
    _validate_mapping_defaults(mapping)

    existing = AEDDatasetMapping.objects.filter(
        organization_mapping=mapping,
        external_dataset_id=external_dataset_id,
    ).select_related("dataset").first()
    if existing:
        if existing.dataset.organization_id != mapping.organization_id:
            raise AEDDataError("The dataset owner no longer matches its mapping.", "dataset_out_of_scope")
        return existing, False

    assigned_dataset_id = payload.get("mcod_dataset_id")
    with transaction.atomic():
        if assigned_dataset_id:
            try:
                dataset = Dataset.objects.get(
                    pk=int(assigned_dataset_id),
                    organization_id=mapping.organization_id,
                )
            except (Dataset.DoesNotExist, TypeError, ValueError):
                raise AEDDataError(
                    "The MCOD dataset does not exist or does not belong to this mapped institution.",
                    "dataset_out_of_scope",
                )
            if AEDDatasetMapping.objects.filter(dataset=dataset).exists():
                raise AEDDataError(
                    "This MCOD dataset already has an AED integration mapping.",
                    "dataset_already_mapped",
                )
        else:
            dataset = Dataset(
                title=title,
                notes=notes,
                url=source_url,
                license_chosen=license_id,
                organization=mapping.organization,
                update_frequency="daily",
                has_dynamic_data=False,
                has_high_value_data=False,
                has_high_value_data_from_ec_list=False,
                has_research_data=False,
                status=Dataset.STATUS.draft,
            )
            try:
                dataset.full_clean()
            except ValidationError as exc:
                raise AEDDataError("The MCOD dataset validation failed: {}".format(exc), "dataset_validation")
            dataset.save()
            dataset.categories.set([mapping.default_category])
            dataset.tags.set(mapping.default_tags.all())

        try:
            dataset_mapping = AEDDatasetMapping.objects.create(
                organization_mapping=mapping,
                external_dataset_id=external_dataset_id,
                dataset=dataset,
            )
            dataset_mapping.full_clean()
        except ValidationError as exc:
            raise AEDDataError("The dataset mapping is invalid: {}".format(exc), "dataset_mapping_invalid")
    return dataset_mapping, True


def update_dataset(mapping, external_dataset_id, payload):
    try:
        dataset_mapping = AEDDatasetMapping.objects.select_related("dataset").get(
            organization_mapping=mapping,
            external_dataset_id=external_dataset_id,
            dataset__organization_id=mapping.organization_id,
        )
    except AEDDatasetMapping.DoesNotExist:
        return None
    dataset = dataset_mapping.dataset
    if "title" in payload:
        title = str(payload["title"]).strip()
        if not title or len(title) > 300:
            raise AEDDataError("title must contain 1–300 characters.", "invalid_title")
        dataset.title = title
    if "description" in payload:
        notes = str(payload["description"]).strip()
        if len(notes) < 20:
            raise AEDDataError("description must contain at least 20 characters.", "invalid_description")
        dataset.notes = notes
    if "source_url" in payload:
        source_url = str(payload["source_url"]).strip()
        if not source_url.startswith("https://"):
            raise AEDDataError("source_url must use HTTPS.", "invalid_source_url")
        dataset.url = source_url
    if "license" in payload:
        dataset.license_chosen = _license_id(str(payload["license"]).strip())
    try:
        dataset.full_clean()
    except ValidationError as exc:
        raise AEDDataError("The MCOD dataset validation failed: {}".format(exc), "dataset_validation")
    dataset.save()
    return dataset_mapping


def get_dataset_mapping(mapping, external_dataset_id):
    try:
        return AEDDatasetMapping.objects.select_related("dataset", "organization_mapping").get(
            organization_mapping=mapping,
            external_dataset_id=external_dataset_id,
            dataset__organization_id=mapping.organization_id,
        )
    except AEDDatasetMapping.DoesNotExist:
        return None


def validate_public_api_url():
    parsed = urlsplit(settings.API_URL)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AEDDataError(
            "Configure API_URL as the public HTTPS MCOD address ending in /api before uploading files.",
            "public_api_url_missing",
        )


def queue_file_validation(resource_file):
    """MCOD's automatic upload signal only validates already-published files."""
    Resource.objects.filter(pk=resource_file.resource_id).update(
        file_tasks_last_status="PENDING",
        data_tasks_last_status="PENDING",
        link_tasks_last_status="PENDING",
        tabular_data_schema=None,
    )

    def enqueue():
        try:
            entrypoint_process_resource_file_validation_task.delay(resource_file.pk)
        except Exception:
            raise AEDDataError(
                "MCOD could not queue file validation; retry the upload after restoring the worker broker.",
                "queue_unavailable",
            )

    transaction.on_commit(enqueue)


def create_or_update_resource(mapping, external_dataset_id, upload, title, description, source_url, resource_id=None):
    validate_public_api_url()
    if not upload or not getattr(upload, "filename", None):
        raise AEDDataError("A CSV or XLSX file is required.", "missing_file")
    filename = upload.filename.split("/")[-1].split("\\")[-1]
    if not filename or len(filename) > 180:
        raise AEDDataError("The uploaded filename is invalid.", "invalid_filename")
    if not title or len(title) > 500:
        raise AEDDataError("title is required and must be at most 500 characters.", "invalid_title")
    if source_url and not source_url.startswith("https://"):
        raise AEDDataError("source_url must use HTTPS.", "invalid_source_url")
    upload_stream = getattr(upload, "stream", None) or getattr(upload, "file", None)
    if upload_stream is None:
        raise AEDDataError("The upload stream is unavailable.", "invalid_file")
    content = upload_stream.read(25 * 1024 * 1024 + 1)
    rows = validate_aed_file(filename, content, external_dataset_id)
    dataset_mapping = get_dataset_mapping(mapping, external_dataset_id)
    if not dataset_mapping:
        raise AEDDataError("The AED dataset is not mapped to an MCOD dataset.", "dataset_not_found")
    dataset = dataset_mapping.dataset
    expected_license = _license_label(dataset.license_chosen)
    if not expected_license or any(row["license"] != expected_license for row in rows):
        raise AEDDataError(
            "Every AED row license must match the mapped MCOD dataset license.",
            "source_license_mismatch",
        )

    if resource_id is not None:
        try:
            resource = Resource.objects.select_related("dataset").get(
                pk=resource_id,
                dataset__organization_id=mapping.organization_id,
                dataset__aed_integration_mapping=dataset_mapping,
            )
        except Resource.DoesNotExist:
            return None, 0
        resource.status = Resource.STATUS.draft
        resource.title = title
        resource.description = description or ""
        resource.data_date = date.today()
        resource.save()
        resource_file = ResourceFile.objects.filter(resource=resource, is_main=True).first()
        uploaded_file = SimpleUploadedFile(
            filename,
            content,
            content_type=upload.content_type or "application/octet-stream",
        )
        if resource_file:
            resource_file.file = uploaded_file
            resource_file.save()
        else:
            resource_file = ResourceFile.objects.create(resource=resource, is_main=True, file=uploaded_file)
        queue_file_validation(resource_file)
        action = "resource_updated"
    else:
        resource = Resource(
            dataset=dataset,
            title=title,
            description=description or "",
            data_date=date.today(),
            status=Resource.STATUS.draft,
            has_dynamic_data=dataset.has_dynamic_data,
            has_high_value_data=dataset.has_high_value_data,
            has_high_value_data_from_ec_list=dataset.has_high_value_data_from_ec_list,
            has_research_data=dataset.has_research_data,
        )
        try:
            resource.full_clean(exclude=("old_resource_type",))
        except ValidationError as exc:
            raise AEDDataError("The MCOD resource validation failed: {}".format(exc), "resource_validation")
        with transaction.atomic():
            resource.save()
            resource_file = ResourceFile.objects.create(
                resource=resource,
                is_main=True,
                file=SimpleUploadedFile(
                    filename,
                    content,
                    content_type=upload.content_type or "application/octet-stream",
                ),
            )
            queue_file_validation(resource_file)
        action = "resource_created"
    write_audit(action, "accepted", mapping=mapping, dataset=dataset, resource=resource)
    resource.refresh_from_db()
    return resource, len(rows)


def resource_status(resource):
    return {
        "resource_id": resource.pk,
        "dataset_id": resource.dataset_id,
        "status": resource.status,
        "file_validation": resource.file_tasks_last_status or "PENDING",
        "data_validation": resource.data_tasks_last_status or "PENDING",
        "link_validation": resource.link_tasks_last_status or "PENDING",
        "file_url": "/api/resources/{}/file".format(resource.pk) if resource.is_published else None,
        "metadata_url": "/api/resources/{}".format(resource.pk) if resource.is_published else None,
    }


def publish_dataset(mapping, external_dataset_id):
    dataset_mapping = get_dataset_mapping(mapping, external_dataset_id)
    if not dataset_mapping:
        return None
    dataset = dataset_mapping.dataset
    if mapping.organization.status != "published":
        raise AEDDataError("The mapped MCOD institution must be published first.", "institution_not_published")
    if not dataset.license_chosen or not dataset.notes or len(dataset.notes.strip()) < 20:
        raise AEDDataError("The MCOD dataset is missing description or license metadata.", "dataset_incomplete")
    if not dataset.tags.exists() or not dataset.categories.exists():
        raise AEDDataError("The MCOD dataset needs its configured tags and category.", "dataset_incomplete")
    dataset.status = Dataset.STATUS.published
    try:
        dataset.full_clean()
    except ValidationError as exc:
        raise AEDDataError("The MCOD dataset validation failed: {}".format(exc), "dataset_validation")
    dataset.save()
    write_audit("dataset_published", "success", mapping=mapping, dataset=dataset)
    return dataset


def publish_resource(mapping, resource_id):
    try:
        resource = Resource.objects.select_related("dataset").get(
            pk=resource_id,
            dataset__organization_id=mapping.organization_id,
            dataset__aed_integration_mapping__organization_mapping=mapping,
        )
    except Resource.DoesNotExist:
        return None
    if resource.dataset.status != Dataset.STATUS.published:
        raise AEDDataError("Publish the MCOD dataset before its resource.", "dataset_not_published")
    if not resource.main_file:
        raise AEDDataError("The resource has no uploaded file.", "missing_file")
    try:
        check_all_resource_validations_status(resource)
    except PendingValidationException:
        raise AEDDataError("MCOD validation is still running.", "validation_pending")
    except FailedValidationException:
        raise AEDDataError("MCOD file validation failed; the resource remains a draft.", "validation_failed")
    resource.status = Resource.STATUS.published
    try:
        resource.full_clean(exclude=("old_resource_type",))
    except ValidationError as exc:
        raise AEDDataError("The MCOD resource validation failed: {}".format(exc), "resource_validation")
    resource.save()
    write_audit("resource_published", "success", mapping=mapping, dataset=resource.dataset, resource=resource)
    return resource


def _fingerprint_source(resource, content):
    digest = hashlib.sha256()
    digest.update(str(resource.pk).encode("utf-8"))
    digest.update(str(resource.dataset_id).encode("utf-8"))
    digest.update(content)
    return digest.hexdigest()


def _duplicate_signature(row):
    def normalized(value):
        value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", value.casefold()).strip()

    try:
        latitude = round(float(row["latitude"]), 3)
        longitude = round(float(row["longitude"]), 3)
    except (TypeError, ValueError):
        latitude, longitude = row.get("latitude", ""), row.get("longitude", "")
    raw = "|".join(
        (
            normalized(row.get("name")),
            normalized(row.get("address")),
            normalized(row.get("city")),
            str(latitude),
            str(longitude),
        )
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def collect_aggregate_rows():
    fingerprint = hashlib.sha256()
    records_by_id = {}
    source_count = 0
    dataset_mappings = AEDDatasetMapping.objects.filter(
        dataset__status=Dataset.STATUS.published,
        dataset__organization_id=F("organization_mapping__organization_id"),
        dataset__organization__status="published",
        organization_mapping__enabled=True,
    ).select_related("dataset", "organization_mapping__organization").order_by("pk")
    for dataset_mapping in dataset_mappings:
        sources = Resource.objects.filter(
            dataset_id=dataset_mapping.dataset_id,
            status=Resource.STATUS.published,
        ).select_related("dataset").prefetch_related("files").order_by("pk")
        for resource in sources:
            main_file = resource.main_file
            if not main_file:
                continue
            with main_file.open("rb") as source_file:
                content = source_file.read()
            fingerprint.update(_fingerprint_source(resource, content).encode("ascii"))
            filename = main_file.name.rsplit("/", 1)[-1]
            rows = validate_aed_file(filename, content, dataset_mapping.external_dataset_id)
            source_count += 1
            for row in rows:
                row.update(
                    {
                        "source_resource_id": str(resource.pk),
                        "source_mcod_dataset_id": str(dataset_mapping.dataset_id),
                        "source_mcod_resource_id": str(resource.pk),
                        "source_mcod_institution_id": str(dataset_mapping.organization_mapping.organization_id),
                        "source_mcod_institution": dataset_mapping.organization_mapping.organization.title,
                    }
                )
                key = row["device_id"].casefold()
                if key in records_by_id:
                    current = records_by_id[key]
                    incoming = row
                    row = dict(incoming if incoming["updated_at"] > current["updated_at"] else current)
                    for field in (
                        "source_dataset_id",
                        "source_resource_id",
                        "source_mcod_dataset_id",
                        "source_mcod_resource_id",
                        "source_mcod_institution_id",
                        "source_mcod_institution",
                        "source_url",
                        "license",
                        "responsible_institution",
                        "verification_evidence_url",
                    ):
                        values = set()
                        for value in (current.get(field, ""), incoming.get(field, "")):
                            values.update(item for item in value.split(";") if item)
                        row[field] = ";".join(sorted(values))
                    row["verification_status"] = (
                        "unverified"
                        if "unverified"
                        in (current.get("verification_status"), incoming.get("verification_status"))
                        else "source_reported"
                    )
                records_by_id[key] = row

    if source_count == 0:
        raise AEDDataError("No published AED source resources are available.", "no_sources")

    duplicate_groups = defaultdict(set)
    for row in records_by_id.values():
        duplicate_groups[_duplicate_signature(row)].add(row["device_id"].casefold())
    for row in records_by_id.values():
        signature = _duplicate_signature(row)
        ids = duplicate_groups[signature]
        row["potential_duplicate"] = "true" if len(ids) > 1 else "false"
        row["duplicate_group"] = signature if len(ids) > 1 else ""
    return list(records_by_id.values()), fingerprint.hexdigest()


def _ensure_aggregate_dataset(state):
    owner = state.owner_mapping
    if not owner or not owner.enabled:
        raise AEDDataError("Configure an enabled MCOD institution mapping as the aggregate owner.", "aggregate_owner_missing")
    if not state.license_chosen:
        raise AEDDataError("Choose the aggregate dataset license in Django admin.", "aggregate_license_missing")
    if owner.organization.status != "published":
        raise AEDDataError("The aggregate owner institution must be published.", "aggregate_owner_not_published")
    _validate_mapping_defaults(owner)
    if state.dataset_id:
        if state.dataset.organization_id != owner.organization_id:
            raise AEDDataError("The aggregate dataset has another owner.", "aggregate_owner_mismatch")
        return state.dataset

    dataset = Dataset(
        title=DATASET_TITLE,
        notes=DATASET_NOTES,
        organization=owner.organization,
        license_chosen=state.license_chosen,
        update_frequency="daily",
        has_dynamic_data=False,
        has_high_value_data=False,
        has_high_value_data_from_ec_list=False,
        has_research_data=False,
        status=Dataset.STATUS.draft,
    )
    dataset.full_clean()
    dataset.save()
    dataset.categories.set([owner.default_category])
    dataset.tags.set(owner.default_tags.all())
    state.dataset = dataset
    state.save(update_fields=("dataset", "updated_at"))
    return dataset


def _license_label(license_id):
    return dict(Dataset.LICENSES).get(license_id)


def _create_aggregate_resource(state, dataset, rows, fingerprint):
    validate_public_api_url()
    if not rows:
        raise AEDDataError("The published source resources contain no AED records.", "empty_aggregate")
    expected_license = _license_label(state.license_chosen)
    source_licenses = {item["license"] for item in rows}
    if source_licenses != {expected_license}:
        raise AEDDataError(
            "All source records must use the administrator-selected aggregate license; "
            "review source licensing before aggregation.",
            "aggregate_license_mismatch",
        )
    if state.pending_resource_id and state.source_fingerprint == fingerprint:
        try:
            return Resource.objects.get(pk=state.pending_resource_id)
        except Resource.DoesNotExist:
            state.pending_resource = None

    csv_bytes = write_csv(rows, AGGREGATE_COLUMNS)
    resource = Resource(
        dataset=dataset,
        title="Ogólnopolski wykaz lokalizacji AED",
        description=(
            "Zbiorczy plik AED z zachowaniem źródeł, licencji i deklarowanego "
            "statusu weryfikacji. Rekordy oznaczone jako source_reported nie są "
            "potwierdzeniem fizycznej weryfikacji urządzenia."
        ),
        data_date=date.today(),
        status=Resource.STATUS.draft,
        has_dynamic_data=False,
        has_high_value_data=False,
        has_high_value_data_from_ec_list=False,
        has_research_data=False,
    )
    resource.full_clean(exclude=("old_resource_type",))
    with transaction.atomic():
        resource.save()
        resource_file = ResourceFile.objects.create(
            resource=resource,
            is_main=True,
            file=SimpleUploadedFile(
                "aed-national-catalog.csv",
                csv_bytes,
                content_type="text/csv",
            ),
        )
        queue_file_validation(resource_file)
        state.pending_resource = resource
        state.source_fingerprint = fingerprint
        state.status = AEDAggregateState.STATUS_BUILDING
        state.last_error = ""
        state.record_count = len(rows)
        state.save(
            update_fields=(
                "pending_resource",
                "source_fingerprint",
                "status",
                "last_error",
                "record_count",
                "updated_at",
            )
        )
    return resource


def rebuild_aggregate_catalog():
    state, _created = AEDAggregateState.objects.get_or_create(singleton=True)
    state.status = AEDAggregateState.STATUS_BUILDING
    state.last_error = ""
    state.save(update_fields=("status", "last_error", "updated_at"))
    rows, fingerprint = collect_aggregate_rows()
    dataset = _ensure_aggregate_dataset(state)
    if (
        state.source_fingerprint == fingerprint
        and state.published_resource_id
        and state.published_resource.status == Resource.STATUS.published
        and not state.pending_resource_id
    ):
        state.status = AEDAggregateState.STATUS_PUBLISHED
        state.last_run_at = timezone.now()
        state.save(update_fields=("status", "last_run_at", "updated_at"))
        return state
    resource = _create_aggregate_resource(state, dataset, rows, fingerprint)
    try:
        check_all_resource_validations_status(resource)
    except PendingValidationException:
        raise
    except FailedValidationException:
        raise AEDDataError(
            "The MCOD validation pipeline rejected the aggregate file.",
            "aggregate_validation_failed",
        )

    with transaction.atomic():
        dataset.refresh_from_db()
        resource.refresh_from_db()
        previous_resource = state.published_resource
        dataset.status = Dataset.STATUS.published
        dataset.save()
        resource.status = Resource.STATUS.published
        resource.save()
        if previous_resource and previous_resource.pk != resource.pk:
            previous_resource.status = Resource.STATUS.draft
            previous_resource.save()
        state.pending_resource = None
        state.published_resource = resource
        state.status = AEDAggregateState.STATUS_PUBLISHED
        state.record_count = len(rows)
        state.last_error = ""
        state.last_run_at = timezone.now()
        state.save(
            update_fields=(
                "pending_resource",
                "published_resource",
                "status",
                "record_count",
                "last_error",
                "last_run_at",
                "updated_at",
            )
        )
        write_audit("aggregate_published", "success", mapping=state.owner_mapping, dataset=dataset, resource=resource)
    return state
