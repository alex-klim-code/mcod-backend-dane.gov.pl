"""Offline safety checks; no database, network, or application changes."""
import unittest
from unittest.mock import patch

from scripts.import_aed_from_dane_gov import assess, relevant
from scripts.aed_import_http import Client, ImportBlocked
from scripts.aed_import_verify import count_records


class ImportSafetyTests(unittest.TestCase):
    def test_irrelevant_fuzzy_search_result_is_rejected(self):
        self.assertFalse(relevant({"title": "Oświetlenie LED"}))
        self.assertTrue(relevant({"title": "Lokalizacja defibrylatorów (AED)"}))

    def test_unknown_size_is_not_downloadable(self):
        bundle = {"dataset": {"id": "1"}, "resources": [{
            "id": "2", "attributes": {"title": "AED", "format": "csv",
                                    "file_url": "https://example.org/file.csv", "file_size": None}
        }]}
        self.assertFalse(assess(bundle, 1024, 2048)["eligible"])

    def test_private_destination_is_rejected_before_http(self):
        client = Client(1024, 2048)
        with patch("scripts.aed_import_http.socket.getaddrinfo",
                   return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ImportBlocked):
                client.request("GET", "https://example.org/file.csv")

    def test_unknown_file_size_never_calls_network(self):
        client = Client(1024, 2048)
        with patch.object(client, "request") as request:
            with self.assertRaises(ImportBlocked):
                client.download("https://example.org/file.csv", None)
            request.assert_not_called()

    def test_pagination_repetition_is_detected(self):
        client = Client(1024, 2048)
        rows = [{"id": str(n)} for n in range(1, 101)]
        with patch.object(client, "json", return_value={"data": rows}):
            with self.assertRaises(ImportBlocked):
                list(client.pages("https://api.dane.gov.pl/datasets", {}))

    def test_csv_with_long_multiline_quoted_values(self):
        import io
        import csv
        data = io.StringIO()
        writer = csv.writer(data, delimiter=";")
        writer.writerow(["nazwa", "opis"])
        for number in range(21):
            writer.writerow(["AED " + str(number), ("opis, lokalizacji\n" * 100)])
        self.assertEqual(count_records(data.getvalue().encode(), "csv"), 21)

    def test_html_is_not_counted_as_csv_data(self):
        with self.assertRaises(ImportBlocked):
            count_records(b"<html>catalogue page</html>", "csv")

    def test_counting_alternative_formats_does_not_claim_unique_devices(self):
        self.assertEqual(count_records(b'{"type":"FeatureCollection","features":[{},{}]}',
                                       "geojson"), 2)
        self.assertIsNone(count_records(b'{"documentation":"not a record collection"}', "json"))


if __name__ == "__main__":
    unittest.main()
