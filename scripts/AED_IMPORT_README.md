# Bezpieczny import publicznych AED

Importer korzysta z istniejących modeli MCOD, oryginalnego przetwarzania plików
i włączonego ResourcesStorage/App Storage. Nie zmienia kodu MCOD ani schematu,
nie importuje kont i nie resetuje bazy.

## Polecenia

```bash
# Aktualne metadane tylko czterech wskazanych zbiorów; bez zapisu i pobierania plików:
bash scripts/replit/python.sh scripts/import_aed_from_dane_gov.py --dry-run --refresh-known --dataset-id 3624 --limit-datasets 1

# Zapis jednego zbioru po udanym dry-run; wznowienie z manifestu:
bash scripts/replit/python.sh scripts/import_aed_from_dane_gov.py --import --resume --dataset-id 3624 --limit-datasets 1

# Odczytowa kontrola zapisanych plików, API, prywatności szkicu i list admina:
bash scripts/replit/python.sh scripts/import_aed_from_dane_gov.py --report --verify

# Samo odtworzenie Markdown z JSON, bez sieci i importu:
bash scripts/replit/python.sh scripts/import_aed_from_dane_gov.py --report

# Testy bez tworzenia bazy testowej:
bash scripts/replit/python.sh -m unittest scripts.test_aed_import scripts.test_aed_original_validation
```

Bez `--refresh-known` lub `--resume` uruchamiane jest wyszukiwanie pięciu fraz
z paginacją po ID i odrzucaniem rozmytych wyników typu LED. Nie jest to
pełny audyt wszystkich zbiorów publicznego katalogu.

## Zabezpieczenia i odwzorowanie

- Domyślnie maksymalnie 10 MiB na plik, 25 MiB na uruchomienie i jeden zbiór.
  Nieznany rozmiar blokuje pobranie. HEAD i GET muszą zgadzać się ze znanym
  rozmiarem; treść jest ograniczana również podczas odczytu.
- Publiczne źródła wymagają HTTPS i publicznych adresów IP, również po
  przekierowaniach. Wyjątek dla wewnętrznego proxy Replit dotyczy tylko
  odrębnego klienta kontrolującego skonfigurowane API własnej instancji.
- Ponawiane są przejściowe błędy sieci, HTTP 429/5xx i limit App Storage.
  Importer ogranicza tempo operacji SDK i współdzieli klienta wyłącznie
  w swoim procesie; nie zmienia serwera ani uwierzytelniania.
- Zastosowano `full_clean()`. Jedynie puste opcjonalne fax/abbreviation
  i nieużywane old_resource_type otrzymują takie wyłączenia, jakie stosują
  istniejące formularze MCOD. Nie wymyśla się wartości zastępczych.
  Niepuste wartości przechodzą walidatory pól modelu, bez przekształcania
  międzynarodowego numeru faksu w krajowy format kontrolki formularza.
- Instytucja, zbiór i zasób mają odrębne lokalne ID. Manifest zachowuje
  identyfikatory i pełne publiczne dokumenty źródłowe, licencje i ich warunki,
  źródłowe URL i daty. Lokalne modified/verified pozostają zarządzane przez MCOD.
- UUID jest rezerwowany w trwałym manifeście przed wstawieniem rekordu.
  Pozwala to wznowić zapis bez przejmowania cudzych rekordów. Manifest jest
  powiązany z bazą; zmiana bazy wymaga osobnego, świadomego procesu.
- Niepowtarzalne nazwy zachowują źródłową nazwę pliku. Istniejący plik nie
  jest nadpisywany. Zmieniony plik źródłowy wymaga osobnej decyzji zamiast
  automatycznej podmiany. Suma SHA-256 kontrolowana jest w App Storage i API.
- Zasoby powstają jako szkice z pustym linkiem. Oryginalne zadanie waliduje
  zapisany plik lokalny i przypisuje wewnętrzny URL. Nie uruchamia się
  pobierania z zewnętrznych linków istniejących zasobów.
- Błąd oryginalnej walidacji zatrzymuje import; nie usuwa się zapisanych
  rekordów ani plików. Przed wznowieniem trzeba wyjaśnić błąd. Ponowne
  uruchomienie nie pobiera ponownie ukończonych plików.

## Wynik wykonania

Pilotaż Krosna zakończono: źródło 3624/54632 → lokalny zbiór/zasób 1/1,
oryginalny CSV 2787 B, 21 wierszy. Powtórzenie nie utworzyło rekordów
ani nie pobrało pliku ponownie.

Przemyśl zaimportowano częściowo. XML, GeoJSON i JSON są opublikowane.
CSV 62095 zachowano jako szkic po błędzie oryginalnego walidatora:
puste wartości w kolumnach 7 i 9 zostały rozpoznane jako nieprawidłowe
liczby całkowite. Nie zmieniono CSV ani nie oznaczono błędu jako sukcesu.
Nie wykonywano dalszych importów po tym błędzie.

Łącznie zapisano 2 instytucje, 2 zbiory, 5 zasobów i 5 oryginalnych
plików, w tym jeden szkic. Marki i pozostały zasób Przemyśla nie zostały
uruchomione. Warszawa ma nieznany rozmiar i URL katalogu zamiast
potwierdzonego pliku JSON.

Każdy zapisany plik ma 21 wierszy. Suma 105 obejmuje alternatywne formaty
tych samych danych, więc nie jest liczbą unikalnych defibrylatorów.

Raport: `reports/aed_import_report.json` i `.md`.
Manifest lokalny: `reports/aed_import_manifest.json`; kopia nadrzędna w
App Storage: `aed-imports/manifest.json`. Historia prób:
`reports/aed-import-runs/`. Test idempotencji pilota:
`reports/aed-pilot-idempotency.json`.
