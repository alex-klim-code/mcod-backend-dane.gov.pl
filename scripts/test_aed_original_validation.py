"""Read-only regression checks; uses model validation without inserting records."""
import os
import unittest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mcod.settings.replit")
import django
django.setup()

from scripts.import_aed_from_dane_gov import inspect_original_validation


class OriginalValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = inspect_original_validation({
            "institution": {"id": "229", "attributes": {"fax": None, "abbreviation": None}}
        })

    def test_null_and_empty_are_rejected_by_model_full_clean(self):
        for name in ("fax", "abbreviation", "old_resource_type"):
            item = self.result[name]
            self.assertTrue(item["null"])
            self.assertFalse(item["blank"])
            self.assertTrue(item["full_clean_field_errors"]["null"])
            self.assertTrue(item["full_clean_field_errors"]["empty_string"])

    def test_original_institution_form_treats_fields_as_optional(self):
        self.assertFalse(self.result["original_form"]["fax_required"])
        self.assertFalse(self.result["original_form"]["abbreviation_required"])


if __name__ == "__main__":
    unittest.main()
