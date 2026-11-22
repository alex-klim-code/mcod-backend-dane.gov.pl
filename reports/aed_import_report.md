# Import publicznych danych AED

Status: **partial_import_halted**

Data UTC: 2026-11-22T02:07:34.427069+00:00

## Wyniki
```json
{
  "imported_institutions": 2,
  "imported_datasets": 2,
  "imported_resources": 5,
  "downloaded_files_this_run": 0,
  "downloaded_bytes_this_run": 0,
  "aed_rows_counted": 105,
  "found_institutions": 4,
  "found_datasets": 4,
  "found_resources": 9,
  "raw_model_empty_field_differences": 3,
  "created_this_run": {
    "institutions": 0,
    "datasets": 0,
    "resources": 0,
    "users": 0
  },
  "stored_original_files": 5,
  "stored_original_bytes": 188676,
  "stored_original_gb": 0.000188676,
  "published_resources": 4,
  "draft_resources": 1,
  "source_file_transfers_recorded": 6,
  "source_bytes_transferred_recorded": 227913
}
```

## Błędy i blokady
- ImportBlocked: Original MCOD validations did not succeed: ['SUCCESS', 'SUCCESS', 'FAILURE']

## Znalezione źródła
| ID zbioru | Tytuł | ID instytucji | ID zasobów | Znane bajty kwalifikujących się plików |
|---|---|---|---|---|
| 3624 | Defibrylatory zlokalizowane w Mieście Krosno | 229 | 54632 | 2787 |
| 4581 | Lokalizacje AED – Automatycznych Defibrylatorów Zewnętrznych w Przemyślu | 145 | 62092, 62093, 62094, 62095, 62424 | 235250 |
| 4955 | Defibrylatory zlokalizowane na terenie Miasta Marki | 537 | 68353, 68355 | 11079 |
| 39512 | Lokalizacja defibrylatorów (AED) | 7621 | 2512040 | 0 |

## Sprawdzone oryginalne pliki
| Zasób źródłowy → lokalny | Zbiór źródłowy → lokalny | Format | Stan | Bajty | Wiersze |
|---|---|---|---|---:|---:|
| 54632 → 1 | 3624 → 1 | csv | published | 2787 | 21 |
| 62092 → 2 | 4581 → 2 | xml | published | 49361 | 21 |
| 62093 → 3 | 4581 → 2 | geojson | published | 48823 | 21 |
| 62094 → 4 | 4581 → 2 | json | published | 48468 | 21 |
| 62095 → 5 | 4581 → 2 | csv | draft | 39237 | 21 |

**Suma wierszy różnych formatów nie jest liczbą unikalnych AED.**
Dla każdego opublikowanego pliku potwierdzono sumę SHA-256 przez oryginalne API. Sprawdzono też, że plik szkicu nie jest publicznie dostępny.

## Oryginalne błędy walidacji CSV
```json
[
  {
    "code": "type-or-format-error",
    "row-number": 2,
    "column-number": 9,
    "message": "The value \"\" in row 2 and column 9 is not type \"integer\" and format \"default\"",
    "message-data": {
      "value": "",
      "field_type": "integer",
      "field_format": "default"
    }
  },
  {
    "code": "type-or-format-error",
    "row-number": 3,
    "column-number": 9,
    "message": "The value \"\" in row 3 and column 9 is not type \"integer\" and format \"default\"",
    "message-data": {
      "value": "",
      "field_type": "integer",
      "field_format": "default"
    }
  },
  {
    "code": "type-or-format-error",
    "row-number": 5,
    "column-number": 9,
    "message": "The value \"\" in row 5 and column 9 is not type \"integer\" and format \"default\"",
    "message-data": {
      "value": "",
      "field_type": "integer",
      "field_format": "default"
    }
  },
  {
    "code": "type-or-format-error",
    "row-number": 6,
    "column-number": 9,
    "message": "The value \"\" in row 6 and column 9 is not type \"integer\" and format \"default\"",
    "message-data": {
      "value": "",
      "field_type": "integer",
      "field_format": "default"
    }
  },
  {
    "code": "type-or-format-error",
    "row-number": 7,
    "column-number": 9,
    "message": "The value \"\" in row 7 and column 9 is not type \"integer\" and format \"default\"",
    "message-data": {
      "value": "",
      "field_type": "integer",
      "field_format": "default"
    }
  },
  {
    "code": "type-or-format-error",
    "row-number": 8,
    "column-number": 9,
    "message": "The value \"\" in row 8 and column 9 is not type \"integer\" and format \"default\"",
    "message-data": {
      "value": "",
      "field_type": "integer",
      "field_format": "default"
    }
  },
  {
    "code": "type-or-format-error",
    "row-number": 9,
    "column-number": 9,
    "message": "The value \"\" in row 9 and column 9 is not type \"integer\" and format \"default\"",
    "message-data": {
      "value": "",
      "field_type": "integer",
      "field_format": "default"
    }
  },
  {
    "code": "type-or-format-error",
    "row-number": 10,
    "column-number": 7,
    "message": "The value \"\" in row 10 and column 7 is not type \"integer\" and format \"default\"",
    "message-data": {
      "value": "",
      "field_type": "integer",
      "field_format": "default"
    }
  },
  {
    "code": "type-or-format-error",
    "row-number": 10,
    "column-number": 9,
    "message": "The value \"\" in row 10 and column 9 is not type \"integer\" and format \"default\"",
    "message-data": {
      "value": "",
      "field_type": "integer",
      "field_format": "default"
    }
  },
  {
    "code": "type-or-format-error",
    "row-number": 11,
    "column-number": 9,
    "message": "The value \"\" in row 11 and column 9 is not type \"integer\" and format \"default\"",
    "message-data": {
      "value": "",
      "field_type": "integer",
      "field_format": "default"
    }
  }
]
```

## Zbiory i licencje
```json
[
  {
    "source_id": "3624",
    "local_id": 1,
    "local_institution_id": 1,
    "title": "Defibrylatory zlokalizowane w Mieście Krosno",
    "source_license": "CC0 1.0",
    "local_license": "CC0 1.0",
    "license_conditions_in_manifest": {
      "license_condition_default_cc40": false,
      "license_condition_timestamp": null,
      "license_condition_original": null,
      "license_condition_custom_description": "",
      "license_condition_personal_data": null,
      "license_condition_db_or_copyrighted": ""
    },
    "status": "published"
  },
  {
    "source_id": "4581",
    "local_id": 2,
    "local_institution_id": 2,
    "title": "Lokalizacje AED – Automatycznych Defibrylatorów Zewnętrznych w Przemyślu",
    "source_license": "CC0 1.0",
    "local_license": "CC0 1.0",
    "license_conditions_in_manifest": {
      "license_condition_default_cc40": false,
      "license_condition_timestamp": null,
      "license_condition_original": null,
      "license_condition_custom_description": "",
      "license_condition_personal_data": null,
      "license_condition_db_or_copyrighted": ""
    },
    "status": "published"
  }
]
```

## Niewykonane etapy
```json
[
  {
    "dataset": "4581",
    "resource": "62095",
    "reason": "Original integer-column validation failed; kept draft."
  },
  {
    "dataset": "4581",
    "resource": "62424",
    "reason": "Not attempted after the validation failure."
  },
  {
    "dataset": "4955",
    "resources": [
      "68353",
      "68355"
    ],
    "reason": "Not attempted after the validation failure."
  },
  {
    "dataset": "39512",
    "resource": "2512040",
    "reason": "Unknown file size; file_url points to an external catalogue, not a verified downloadable JSON file."
  }
]
```

## Daty i panel
Exact source timestamps are retained in the durable manifest. MCOD assigns its own local modified/verified timestamps during publication and validation; these were not forcibly overwritten.
Listy oryginalnego panelu wyrenderowano testem z uprawnieniami istniejącego pracownika, bez utworzenia sesji. Nie weryfikowano zalogowanego panelu w przeglądarce.

Kolumna znanych bajtów w tabeli znalezionych źródeł pochodzi z metadanych API. Tabela sprawdzonych plików podaje rozmiary zmierzone podczas kontroli App Storage.
Brak rozmiaru nie oznacza pliku o zerowej wielkości.

## Kontrole
```json
{
  "import_api_tests": "not_run_no_import",
  "original_validation": {
    "fax": {
      "null": true,
      "blank": false,
      "choices": [],
      "full_clean_field_errors": {
        "null": [
          "To pole nie może być puste."
        ],
        "empty_string": [
          "To pole nie może być puste."
        ]
      }
    },
    "abbreviation": {
      "null": true,
      "blank": false,
      "choices": [],
      "full_clean_field_errors": {
        "null": [
          "To pole nie może być puste."
        ],
        "empty_string": [
          "To pole nie może być puste."
        ]
      }
    },
    "old_resource_type": {
      "null": true,
      "blank": false,
      "choices": [],
      "full_clean_field_errors": {
        "null": [
          "To pole nie może być puste."
        ],
        "empty_string": [
          "To pole nie może być puste."
        ]
      }
    },
    "source_institution": {
      "id": "145",
      "fax": "0048166786449",
      "abbreviation": null
    },
    "original_form": {
      "fax_required": false,
      "abbreviation_required": false,
      "mechanism": "Django ModelForm._get_validation_exclusions excludes empty optional form fields before calling instance.full_clean(exclude=...). This differs from unrestricted model.full_clean()."
    }
  },
  "code_unchanged": true,
  "schema_unchanged": true,
  "before": {
    "mcod_code_sha256": "640a77a54e14f418163a988f937584ee95b6ac2599f4f51cfb441c4419f6c2c6",
    "schema_sha256": "ef4e9d72391cfa654ee2f3ee63883b55c2b2478f8b22b1c7404e7914b1388284",
    "counts": {
      "institutions": 2,
      "datasets": 2,
      "resources": 5,
      "users": 1
    }
  },
  "after": {
    "mcod_code_sha256": "640a77a54e14f418163a988f937584ee95b6ac2599f4f51cfb441c4419f6c2c6",
    "schema_sha256": "ef4e9d72391cfa654ee2f3ee63883b55c2b2478f8b22b1c7404e7914b1388284",
    "counts": {
      "institutions": 2,
      "datasets": 2,
      "resources": 5,
      "users": 1
    }
  },
  "admin": {
    "institution": {
      "status": 200,
      "visible_local_ids": [
        1,
        2
      ],
      "method": "Original admin view rendered in process with existing staff; no login/session created."
    },
    "dataset": {
      "status": 200,
      "visible_local_ids": [
        1,
        2
      ],
      "method": "Original admin view rendered in process with existing staff; no login/session created."
    },
    "resource": {
      "status": 200,
      "visible_local_ids": [
        1,
        2,
        3,
        4,
        5
      ],
      "method": "Original admin view rendered in process with existing staff; no login/session created."
    }
  },
  "signed_in_browser_ui": "not_verified; original admin rendered in an in-process test",
  "all_stored_original_checksums_match": true,
  "public_download_checksums_match": true,
  "pilot_idempotency": {
    "created": {
      "institutions": 0,
      "datasets": 0,
      "resources": 0,
      "users": 0
    },
    "source_files_downloaded": 0,
    "status": "imported"
  },
  "final_read_only_check": {
    "counts_unchanged": true,
    "code_unchanged": true,
    "schema_unchanged": true
  }
}
```

## Importowane identyfikatory
```json
{}
```

## Zakres i ograniczenia
Five requested keyword searches with ID-cursor pagination, then AED/defibrylat matching in public metadata. This does not prove detection of every unlabelled or otherwise unsearchable AED dataset.

Walidacja odpowiada istniejącym formularzom MCOD: pusty opcjonalny faks i skrót oraz historyczne old_resource_type są wyłączane tak jak w panelu administratora. Pozostałe pola, model.clean(), unikalność i relacje przechodzą full_clean(). Nie wpisano fikcyjnego faksu, skrótu ani typu historycznego.
Pliki zachowują oryginalne bajty. Liczby wierszy nie oznaczają unikalnych AED: różne formaty i wersje mogą opisywać te same urządzenia.
Nie są importowane konta, hasła, sesje ani uprawnienia. Nie są zmieniane modele, schemat ani oryginalny kod MCOD.
