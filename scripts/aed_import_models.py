"""Strict preflight for the additive importer; never fabricate mandatory fields."""
from django.core.exceptions import ValidationError
from django.utils.translation import override

from mcod.organizations.models import Organization
from mcod.datasets.models import Dataset, UPDATE_FREQUENCY
from mcod.resources.models import Resource, ResourceFile

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


def preflight(bundle, assessment):
    storage = ResourceFile._meta.get_field("file").storage
    if not getattr(storage, "app_storage_enabled", False):
        raise ImportBlocked("Existing MCOD ResourcesStorage must have App Storage enabled.")
    storage._app_storage_client().exists("aed-imports/manifest.json")
    oa = bundle["institution"]["attributes"]
    organization = Organization(**public_values(Organization, oa, (
        "title", "description", "postal_code", "city", "street_type", "street",
        "street_number", "flat_number", "email", "epuap", "fax", "institution_type",
        "electronic_delivery_address", "regon", "tel", "website", "abbreviation",
    )), status="draft")
    # This is intentionally strict: nullable-but-required fields are not invented
    # and no validator is bypassed to make an incompatible source import succeed.
    errors = {}
    try:
        organization.full_clean()
    except ValidationError as exc:
        errors["institution:" + bundle["institution"]["id"]] = exc.message_dict
    da = bundle["dataset"]["attributes"]
    ds_values = public_values(Dataset, da, (
        "title", "notes", "url", "license_chosen", "license_condition_db_or_copyrighted",
        "license_condition_default_cc40", "license_condition_personal_data",
        "license_condition_timestamp", "license_condition_original",
        "license_condition_custom_description", "has_dynamic_data", "has_high_value_data",
        "has_high_value_data_from_ec_list", "has_research_data",
    ))
    # Match the publicly stated license exactly; never substitute unknown terms.
    if not ds_values.get("license_chosen"):
        choices = {str(label): code for code, label in Dataset.LICENSES}
        name = da.get("license_name")
        if name not in choices:
            errors["dataset_license"] = "Unknown source license: {!r}".format(name)
        else:
            ds_values["license_chosen"] = choices[name]
    with override("pl"):
        choices = {str(label): value for value, label in UPDATE_FREQUENCY}
    # Published API labels may differ from the translations bundled in this fork.
    choices.update({"Nie dotyczy": "notApplicable", "Codziennie": "daily",
                    "Jednorazowe udostępnienie": "notPlanned"})
    frequency = da.get("update_frequency")
    if frequency not in choices:
        errors["update_frequency"] = "Unrecognized source frequency: {!r}".format(frequency)
    else:
        ds_values["update_frequency"] = choices[frequency]
    for resource in assessment["files"]:
        a = resource["attributes"]
        values = public_values(Resource, a, (
            "title", "description", "data_date", "language", "has_dynamic_data",
            "has_high_value_data", "has_high_value_data_from_ec_list", "has_research_data",
        ))
        obj = Resource(**values, status="draft")
        # Parent FK cannot be checked before saving a parent; all other original
        # field validators remain enabled, including required legacy fields.
        try:
            obj.full_clean(exclude=("dataset",))
        except ValidationError as exc:
            errors["resource:" + resource["id"]] = exc.message_dict
    if errors:
        raise ImportBlocked(
            "Original MCOD validators prevent import; no records or files were written. "
            "Source values were not fabricated and application code was not changed. {!r}".format(errors)
        )
    return {"organization": organization, "dataset_values": ds_values}


def import_bundle(bundle, assessment, prepared, client, manifest_path, resume):
    # Publication has asynchronous side effects. Do not expose a write path until
    # strict source preflight can succeed and those side effects are verified.
    raise ImportBlocked(
        "Write stage is disabled pending successful original-model preflight and "
        "verification of publication side effects. No partial import is performed."
    )
