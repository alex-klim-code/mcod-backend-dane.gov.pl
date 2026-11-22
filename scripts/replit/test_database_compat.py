"""Offline tests: no secrets, network, or real database connections."""

import unittest

from mcod.settings.database_compat import neon_compatible_database


class NeonCompatibilityTests(unittest.TestCase):
    def database(self, host="ep-example-123.eu-central-1.aws.neon.tech", **options):
        return {"ENGINE": "django.db.backends.postgresql", "HOST": host, "OPTIONS": options}

    def test_legacy_client_gets_endpoint(self):
        result = neon_compatible_database(self.database(), 110005)
        self.assertEqual(result["OPTIONS"]["options"], "endpoint=ep-example-123")

    def test_pooler_suffix_is_not_part_of_endpoint(self):
        database = self.database("ep-example-123-pooler.eu-central-1.aws.neon.tech")
        result = neon_compatible_database(database, 110005)
        self.assertEqual(result["OPTIONS"]["options"], "endpoint=ep-example-123")

    def test_preserves_tls_and_existing_startup_options(self):
        database = self.database(sslmode="require", options="-c statement_timeout=5000")
        result = neon_compatible_database(database, 110005)
        self.assertEqual(result["OPTIONS"]["sslmode"], "require")
        self.assertEqual(
            result["OPTIONS"]["options"],
            "-c statement_timeout=5000 endpoint=ep-example-123",
        )

    def test_does_not_override_explicit_endpoint(self):
        for option in ("endpoint=ep-explicit", "-c endpoint=ep-explicit"):
            database = self.database(options=option)
            self.assertEqual(neon_compatible_database(database, 110005), database)

    def test_modern_client_uses_sni(self):
        database = self.database(sslmode="verify-full")
        self.assertEqual(neon_compatible_database(database, 140000), database)

    def test_local_database_is_unchanged(self):
        database = self.database("127.0.0.1", options="-c statement_timeout=1000")
        self.assertEqual(neon_compatible_database(database, 110005), database)

    def test_unrecognized_host_cannot_inject_options(self):
        for host in ("other.neon.tech", "ep-example.neon.tech.attacker.invalid",
                     "ep-example,other.neon.tech"):
            database = self.database(host)
            self.assertEqual(neon_compatible_database(database, 110005), database)

    def test_original_configuration_is_not_mutated(self):
        database = self.database(sslmode="require")
        neon_compatible_database(database, 110005)
        self.assertEqual(database["OPTIONS"], {"sslmode": "require"})

    def test_missing_options_are_supported(self):
        database = self.database()
        del database["OPTIONS"]
        result = neon_compatible_database(database, 110005)
        self.assertEqual(result["OPTIONS"]["options"], "endpoint=ep-example-123")


if __name__ == "__main__":
    unittest.main()
