"""Additive importer using the same empty-field rules as the original MCOD forms."""
import hashlib
import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit, unquote

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.forms import modelform_factory
from django.db import transaction, connection
from django.utils.dateparse import parse_datetime
from django.utils.translation import override

from mcod.organizations.models import Organization
from mcod.organizations.forms import OrganizationForm
from mcod.datasets.models import Dataset, UPDATE_FREQUENCY
from mcod.resources.models import Resource, ResourceFile
from mcod.resources.forms import ChangeResourceForm

from scripts.aed_import_http import ImportBlocked


def public_values(model, attrs, allowed):
    values = {}
    for name in allowed:
        if name in attrs:
            field = model._meta.get_field(name)
            value = attrs[name]
            if value is None and not field.null:
                continue
            values[name] = value
    return values


def clean_original(obj, parent_pending=False):
    """No fake values: follow the existing ModelForm's explicit exclusions."""
    exclude = []
    if isinstance(obj, Organization):
        form_type = modelform_factory(Organization, form=OrganizationForm,
                                     fields=("title", "fax", "abbreviation"))
        form = form_type()
        for name in ("fax", "abbreviation"):
            value = getattr(obj, name)
            # Use the form only to decide whether an empty input is allowed.
            # Nonempty stored values go through the MODEL field validators:
            # the public API can contain an international fax, whereas the UI's
            # input widget accepts only its nine-digit national portion.
            if not form.fields[name].required and value in form.fields[name].empty_values:
                form.fields[name].clean(value)
                exclude.append(name)
    if isinstance(obj, Resource):
        # Unused legacy nullable field; original ResourceForm excludes it too.
        if "old_resource_type" not in ChangeResourceForm.Meta.exclude:
            raise ImportBlocked("Original resource form validation rules changed.")
        exclude.append("old_resource_type")
        if parent_pending:
            exclude.append("dataset")
    if isinstance(obj, Dataset) and parent_pending:
        exclude.append("organization")
    obj.full_clean(exclude=exclude)
    return obj


def source_dates(obj, attrs):
    for name in ("created", "modified", "verified"):
        if attrs.get(name) and hasattr(obj, name):
            value = parse_datetime(attrs[name])
            if not value:
                raise ImportBlocked("Invalid original {} timestamp.".format(name))
            setattr(obj, name, value)
    return obj


def preflight(bundle, assessment):
    storage = ResourceFile._meta.get_field("file").storage
    if not getattr(storage, "app_storage_enabled", False):
        raise ImportBlocked("Existing ResourcesStorage must have App Storage enabled.")
    storage._app_storage_client().exists("aed-imports/manifest.json")
    owned = Manifest("reports/aed_import_manifest.json").state["objects"]

    def identity(obj, kind, source_id):
        entry = owned.get(kind + ":" + source_id)
        if entry:
            existing = type(obj).objects.filter(uuid=entry["uuid"]).first()
            if existing:
                obj.pk, obj.uuid = existing.pk, existing.uuid
                obj._state.adding = False
        return obj

    oa = bundle["institution"]["attributes"]
    organization = Organization(**public_values(Organization, oa, (
        "title", "description", "postal_code", "city", "street_type", "street",
        "street_number", "flat_number", "email", "epuap", "fax", "institution_type",
        "electronic_delivery_address", "regon", "tel", "website", "abbreviation",
    )), status="draft")
    source_dates(organization, oa)
    identity(organization, "institution", bundle["institution"]["id"])
    da = bundle["dataset"]["attributes"]
    ds_values = public_values(Dataset, da, (
        "title", "notes", "url", "license_chosen", "license_condition_db_or_copyrighted",
        "license_condition_default_cc40", "license_condition_personal_data",
        "license_condition_timestamp", "license_condition_original",
        "license_condition_custom_description", "has_dynamic_data", "has_high_value_data",
        "has_high_value_data_from_ec_list", "has_research_data",
    ))
    if not ds_values.get("license_chosen"):
        names = {str(label): code for code, label in Dataset.LICENSES}
        if da.get("license_name") not in names:
            raise ImportBlocked("Unknown source license: {!r}".format(da.get("license_name")))
        ds_values["license_chosen"] = names[da["license_name"]]
    if dict(Dataset.LICENSES).get(ds_values["license_chosen"]) != da.get("license_name"):
        raise ImportBlocked("License ID and original license name disagree.")
    with override("pl"):
        frequencies = {str(label): code for code, label in UPDATE_FREQUENCY}
    frequencies.update({"Nie dotyczy": "notApplicable", "Codziennie": "daily",
                        "Jednorazowe udostępnienie": "notPlanned"})
    frequency = da.get("update_frequency")
    if frequency is not None and frequency not in frequencies:
        raise ImportBlocked("Unrecognized source frequency: {!r}".format(frequency))
    ds_values["update_frequency"] = frequencies.get(frequency)
    errors = {}
    try:
        clean_original(organization)
    except ValidationError as exc:
        errors["institution"] = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
    dataset = source_dates(Dataset(**ds_values, status="draft"), da)
    identity(dataset, "dataset", bundle["dataset"]["id"])
    try:
        clean_original(dataset, parent_pending=True)
    except ValidationError as exc:
        errors["dataset"] = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
    resource_values = {}
    for source in assessment["files"]:
        if source["relationships"]["dataset"]["data"]["id"] != bundle["dataset"]["id"]:
            raise ImportBlocked("Resource refers to another source dataset.")
        values = public_values(Resource, source["attributes"], (
            "title", "description", "data_date", "language", "has_dynamic_data",
            "has_high_value_data", "has_high_value_data_from_ec_list", "has_research_data",
        ))
        resource_values[source["id"]] = values
        obj = source_dates(Resource(**values, status="draft"), source["attributes"])
        identity(obj, "resource", source["id"])
        try:
            clean_original(obj, parent_pending=True)
        except ValidationError as exc:
            errors["resource:" + source["id"]] = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
    if errors:
        raise ImportBlocked("Original model/form validation failed: {!r}".format(errors))
    return {"organization": organization, "dataset_values": ds_values,
            "resource_values": resource_values}


class Manifest:
    """App Storage is authoritative; reserve UUIDs before inserting any row."""
    key = "aed-imports/manifest.json"

    def __init__(self, path):
        self.path = Path(path)
        self.client = ResourceFile._meta.get_field("file").storage._app_storage_client()
        binding = hashlib.sha256(json.dumps(
            {key: str(connection.settings_dict[key]) for key in ("HOST", "PORT", "NAME")},
            sort_keys=True).encode()).hexdigest()
        if self.client.exists(self.key):
            self.state = json.loads(self.client.download_as_bytes(self.key))
            if self.state.get("database_binding") != binding:
                raise ImportBlocked("Manifest belongs to a different database; do not reuse IDs.")
        else:
            self.state = {"version": 1, "database_binding": binding, "objects": {}, "files": {}}

    def save(self):
        data = json.dumps(self.state, ensure_ascii=False, indent=2).encode()
        self.client.upload_from_bytes(self.key, data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_bytes(data)
        temp.replace(self.path)

    def object(self, model, kind, source, build):
        key = kind + ":" + source["id"]
        entry = self.state["objects"].get(key)
        if entry is None:
            entry = {"uuid": str(uuid.uuid4()), "source_id": source["id"],
                     "source_url": source["links"]["self"], "source": source}
            self.state["objects"][key] = entry
            self.save()
        obj = model.objects.filter(uuid=entry["uuid"]).first()
        if obj is None:
            if entry.get("local_id"):
                raise ImportBlocked("Manifest-owned record is missing; refusing recreation.")
            obj = build()
            obj.uuid = uuid.UUID(entry["uuid"])
            if hasattr(obj, "ext_ident"):
                obj.ext_ident = source["id"]
            clean_original(obj)
            obj.save()
        elif entry.get("local_id") and obj.pk != entry["local_id"]:
            raise ImportBlocked("Manifest local ID does not match its reserved UUID.")
        entry["local_id"] = obj.pk
        self.save()
        return obj


def import_bundle(bundle, assessment, prepared, client, manifest_path, resume):
    from django.conf import settings
    from mcod.categories.models import Category
    from mcod.resources.tasks import entrypoint_process_resource_file_validation_task
    from scripts.aed_import_verify import count_records, verify_import

    if assessment["skipped"]:
        raise ImportBlocked("Dataset has ineligible resources; refusing a silently partial import.")
    manifest = Manifest(manifest_path)
    org = manifest.object(Organization, "institution", bundle["institution"],
                          lambda: prepared["organization"])

    def new_dataset():
        return source_dates(Dataset(organization=org, status="draft", **prepared["dataset_values"]),
                            bundle["dataset"]["attributes"])

    dataset = manifest.object(Dataset, "dataset", bundle["dataset"], new_dataset)
    if dataset.organization_id != org.pk:
        raise ImportBlocked("Existing manifest dataset belongs to a different institution.")
    if dataset.status != "published":
        codes = [c["code"] for c in bundle["dataset"]["attributes"].get("categories", [])]
        dataset.categories.set(Category.objects.filter(code__in=codes))
    results = []
    for source in assessment["files"]:
        attrs = source["attributes"]
        key = source["id"]
        entry = manifest.state["files"].get(key)
        if entry and entry.get("source_modified") != attrs.get("modified"):
            raise ImportBlocked("Source changed; original imported files will not be overwritten.")

        def new_resource():
            return source_dates(Resource(dataset=dataset, status="draft",
                                         **prepared["resource_values"][key]), attrs)

        resource = manifest.object(Resource, "resource", source, new_resource)
        if resource.dataset_id != dataset.pk:
            raise ImportBlocked("Existing manifest resource belongs to another dataset.")
        storage = ResourceFile._meta.get_field("file").storage
        if not entry:
            content = client.download(attrs["file_url"], attrs["file_size"])
            original_name = unquote(urlsplit(attrs["file_url"]).path.rsplit("/", 1)[-1])
            if not original_name or "/" in original_name or "\\" in original_name:
                raise ImportBlocked("Unsafe original filename.")
            row_count = count_records(content, attrs["format"])
            file_obj = ResourceFile(resource=resource, is_main=True)
            name = "aed-imports/institution-{}/dataset-{}/resource-{}/{}/{}".format(
                bundle["institution"]["id"], bundle["dataset"]["id"], key, uuid.uuid4().hex,
                original_name)
            generated = file_obj.file.field.generate_filename(file_obj, name)
            if storage._app_storage_client().exists(generated) or storage.exists(generated):
                raise ImportBlocked("Target file already exists; refusing overwrite.")
            entry = {"storage_name": generated, "sha256": hashlib.sha256(content).hexdigest(),
                     "bytes": len(content), "records": row_count,
                     "source_modified": attrs.get("modified"), "source_url": attrs["file_url"],
                     "original_name": original_name, "format": attrs["format"], "phase": "reserved"}
            manifest.state["files"][key] = entry
            manifest.save()
            file_obj.file.save(name, ContentFile(content), save=False)
            if file_obj.file.name != generated:
                raise ImportBlocked("Storage changed reserved filename.")
            file_obj.full_clean()
            file_obj.save()
            entry["file_id"] = file_obj.pk
            entry["phase"] = "stored"
            manifest.save()
        else:
            file_obj = ResourceFile.objects.filter(resource=resource, file=entry["storage_name"]).first()
            if not file_obj:
                if not storage._app_storage_client().exists(entry["storage_name"]):
                    raise ImportBlocked("Reserved file missing; no automatic duplicate download.")
                file_obj = ResourceFile(resource=resource, is_main=True, file=entry["storage_name"])
                file_obj.full_clean()
                file_obj.save()
            entry["file_id"] = file_obj.pk
        remote = storage._app_storage_client().download_as_bytes(entry["storage_name"])
        if hashlib.sha256(remote).hexdigest() != entry["sha256"]:
            raise ImportBlocked("App Storage checksum verification failed.")
        entry["app_storage_verified"] = True
        manifest.save()
        resource.refresh_from_db()
        if resource.status != "published":
            # Only local files are validated. The link remains empty until this
            # existing task assigns the internal MCOD download URL.
            if resource.link and not resource.is_link_internal:
                raise ImportBlocked("External link could trigger an uncontrolled downloader.")
            result = entrypoint_process_resource_file_validation_task.apply(
                args=(file_obj.pk,), kwargs={"update_file_archive": False,
                                            "update_verification_date": False})
            if result.failed():
                raise ImportBlocked("Original file validation task failed: " + str(result.result))
            resource = Resource.objects.get(pk=resource.pk)
            statuses = [resource.file_tasks_last_status, resource.link_tasks_last_status]
            if resource.is_data_processable:
                statuses.append(resource.data_tasks_last_status)
            if any(status != "SUCCESS" for status in statuses):
                raise ImportBlocked("Original MCOD validations did not succeed: " + repr(statuses))
            if org.status != "published":
                org.status = "published"
                clean_original(org)
                org.save()
            if dataset.status != "published":
                dataset.status = "published"
                clean_original(dataset)
                dataset.save()
            resource.status = "published"
            clean_original(resource)
            resource.save()
        entry["phase"] = "published"
        manifest.save()
        checks = verify_import(org, dataset, resource, entry, settings.API_URL, client)
        entry["verification"] = checks
        manifest.save()
        results.append({"source_resource_id": key, "local_resource_id": resource.pk,
                        **entry})
    return {"source_dataset_id": bundle["dataset"]["id"], "local_dataset_id": dataset.pk,
            "source_institution_id": bundle["institution"]["id"], "local_institution_id": org.pk,
            "resources": results}
