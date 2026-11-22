"""Dataset values are declared by the publisher, not fabricated to pass validation."""

from django.core.exceptions import ValidationError

from mcod.aed_integration.validation import AEDDataError
from mcod.datasets.forms import UPDATE_FREQUENCY_FOR_CREATE
from mcod.lib.metadata_validators import (
    validate_conflicting_high_value_data_flags,
    validate_high_value_data_from_ec_list_organization,
)


DATASET_FLAGS = (
    "has_dynamic_data", "has_high_value_data",
    "has_high_value_data_from_ec_list", "has_research_data",
)


def dataset_options(payload, organization, partial=False, instance=None):
    result = {}
    for name in DATASET_FLAGS:
        if partial and name not in payload:
            continue
        if type(payload.get(name)) is not bool:
            raise AEDDataError("{} must be explicitly true or false.".format(name), "dataset_classification_required")
        result[name] = payload[name]
    if not partial or "update_frequency" in payload:
        frequency = payload.get("update_frequency")
        if frequency not in {key for key, _label in UPDATE_FREQUENCY_FOR_CREATE if key}:
            raise AEDDataError("Declare a native MCOD update_frequency.", "invalid_update_frequency")
        result["update_frequency"] = frequency
    ec_list = result.get(
        "has_high_value_data_from_ec_list",
        getattr(instance, "has_high_value_data_from_ec_list", False),
    )
    try:
        validate_conflicting_high_value_data_flags(
            result.get("has_high_value_data", getattr(instance, "has_high_value_data", False)), ec_list,
        )
        validate_high_value_data_from_ec_list_organization(ec_list, organization.institution_type)
    except ValidationError as exc:
        raise AEDDataError(str(exc), "dataset_classification_invalid")
    return result
