# Przykłady dla backendu AED Puls

`MCOD_API_BASE_URL` musi wskazywać faktycznie opublikowany MCOD, kończąc się `/api`.
Wartość sekretu pobieraj ze zmiennych środowiskowych backendu. Przykłady nie
zawierają prawdziwych tokenów.

## 1. Lista przypisanych instytucji

```bash
curl --fail-with-body "$MCOD_API_BASE_URL/integrations/aed/v1/institutions" \
  -H "Authorization: Bearer $MCOD_INTEGRATION_SECRET"
```

Odpowiedź `200`:
```json
{"data":[{"external_organization_id":"org-a","mcod_institution_id":10,
"name":"Instytucja A","status":"published","mcod_api_url":"/api/institutions/10"}]}
```

Przykładowe ID służą tylko ilustracji, nie oznaczają rekordów w tej bazie.

## 2. Utworzenie zbioru

```bash
curl --fail-with-body -X POST \
  "$MCOD_API_BASE_URL/integrations/aed/v1/organizations/org-a/datasets" \
  -H "Authorization: Bearer $MCOD_INTEGRATION_SECRET" \
  -H "Content-Type: application/json" \
  --data '{"external_dataset_id":"aed-a","title":"Lokalizacje AED instytucji A",
  "description":"Lokalizacje defibrylatorów utrzymywane przez instytucję A.",
  "source_url":"https://example.org/aed-a","license":"CC0 1.0"}'
```

`201` dla nowego przypisania lub `200` dla istniejącego:
```json
{"external_dataset_id":"aed-a","dataset_id":20,"status":"draft",
"metadata_url":"/api/datasets/20"}
```

Opcjonalny `mcod_dataset_id` przypisuje istniejący zbiór wyłącznie tej instytucji.
Adapter nie zmienia jego właściciela. Publikacja zbioru:

```bash
curl --fail-with-body -X POST \
  "$MCOD_API_BASE_URL/integrations/aed/v1/organizations/org-a/datasets/aed-a/publish" \
  -H "Authorization: Bearer $MCOD_INTEGRATION_SECRET"
```

## 3. Minimalny plik CSV

```csv
device_id,name,latitude,longitude,availability,hours,status,updated_at,responsible_institution,source_dataset_id,source_url,license,verification_status
aed-a-001,AED w urzędzie,52.2297,21.0122,public,24/7,available,2026-11-20,Instytucja A,aed-a,https://example.org/aed-a,CC0 1.0,source_reported
```

To syntetyczny przykład, nie potwierdzenie lokalizacji urządzenia.

## 4. Wysłanie, stan, publikacja i aktualizacja zasobu

```bash
curl --fail-with-body -X POST \
  "$MCOD_API_BASE_URL/integrations/aed/v1/organizations/org-a/datasets/aed-a/resources" \
  -H "Authorization: Bearer $MCOD_INTEGRATION_SECRET" \
  -F "title=Lokalizacje AED" -F "file=@aed.csv"
```

Odpowiedź `202` zawiera `resource_id`, `dataset_id`, `accepted_rows`,
`status: "draft"` oraz `file_validation`, `data_validation`, `link_validation`.
Gdy plik jest szkicem, `file_url` i `metadata_url` są `null`.

```bash
curl --fail-with-body \
  "$MCOD_API_BASE_URL/integrations/aed/v1/organizations/org-a/resources/30" \
  -H "Authorization: Bearer $MCOD_INTEGRATION_SECRET"

curl --fail-with-body -X POST \
  "$MCOD_API_BASE_URL/integrations/aed/v1/organizations/org-a/resources/30/publish" \
  -H "Authorization: Bearer $MCOD_INTEGRATION_SECRET"

curl --fail-with-body -X PUT \
  "$MCOD_API_BASE_URL/integrations/aed/v1/organizations/org-a/resources/30" \
  -H "Authorization: Bearer $MCOD_INTEGRATION_SECRET" \
  -F "external_dataset_id=aed-a" -F "title=Aktualizacja AED" -F "file=@aed-updated.csv"
```

Po `PUT` wymagane są ponowna walidacja i publikacja.

## 5. Agregacja

```bash
curl --fail-with-body -X POST \
  "$MCOD_API_BASE_URL/integrations/aed/v1/aggregate" \
  -H "Authorization: Bearer $MCOD_INTEGRATION_SECRET"
curl --fail-with-body "$MCOD_API_BASE_URL/integrations/aed/v1/aggregate" \
  -H "Authorization: Bearer $MCOD_INTEGRATION_SECRET"
```

`POST` zwraca `202 {"status":"queued","task_id":"..."}`.
`GET` zwraca rzeczywisty stan, liczbę rekordów, czas i kod błędu,
ID zbioru/zasobu oraz URL ostatniego opublikowanego pliku.
Pobierz plik używając oryginalnego `GET /resources/{id}/file`
(przekierowanie do pliku MCOD). Nie wysyłaj sekretu do URL źródłowych.

## Błędy adaptera

```json
{"error":{"code":"validation_pending","message":"MCOD validation is still running."}}
```

- `400`: wymagane HTTPS albo nieprawidłowe dane żądania.
- `401`: brak lub błędny bearer.
- `404`: brak mapowania albo obiekt poza wskazaną instytucją.
- `409`: walidacja trwa lub brak konfiguracji właściciela agregatu.
- `413`: za duży plik.
- `422`: błędy danych, niespójna licencja lub nieudana walidacja MCOD.
- `503`: brak sekretu integracji albo niedostępna kolejka.

Nie ponawiaj automatycznie `POST` tworzenia zasobu po utracie odpowiedzi:
najpierw sprawdź listę zasobów zbioru. Tworzenie zbiorów jest idempotentne
według pary `(external_organization_id, external_dataset_id)`.
