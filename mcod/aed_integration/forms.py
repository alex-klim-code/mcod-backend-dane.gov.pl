"""Integration forms reuse the portal's validators, not a second institution model."""

from mcod.organizations.forms import OrganizationForm


INSTITUTION_FIELDS = (
    "title", "description", "institution_type", "postal_code", "city", "street_type",
    "street", "street_number", "flat_number", "email", "tel", "tel_internal",
    "fax", "fax_internal", "epuap", "regon", "website", "abbreviation",
    "electronic_delivery_address", "status",
)


class AEDInstitutionForm(OrganizationForm):
    class Meta(OrganizationForm.Meta):
        fields = INSTITUTION_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # OrganizationForm also declares user assignments/translations explicitly.
        # They are not part of the integration's institution-edit permission.
        for name in list(self.fields):
            if name not in INSTITUTION_FIELDS:
                self.fields.pop(name)

