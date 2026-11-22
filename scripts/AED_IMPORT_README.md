# Import AED — zatrzymany na walidacji

Skrypt wykonuje wyszukiwanie pięcioma wskazanymi frazami, paginację po ID,
filtrację wyników rozmytych, odczyt instytucji i zasobów, ocenę rozmiarów oraz
walidację bez zapisu. Nie zmienia kodu aplikacji, tabel, migracji ani integracji.

```bash
bash scripts/replit/python.sh scripts/import_aed_from_dane_gov.py --dry-run --limit-datasets 1
bash scripts/replit/python.sh scripts/import_aed_from_dane_gov.py --dry-run --resume --limit-datasets 1
bash scripts/replit/python.sh scripts/import_aed_from_dane_gov.py --report
bash scripts/replit/python.sh -m unittest scripts.test_aed_import
```

`--resume` wznawia obecnie z kompletnego lokalnego wyniku wyszukiwania.
Nie jest jeszcze checkpointem częściowo wykonanego importu.
`--dataset-id` wybiera konkretny zbiór z wyników.
Domyślne limity wynoszą 10 MiB na plik i 25 MiB łącznie. Nieznane rozmiary
blokują pobranie. Nie pobiera się całego katalogu.

## Stan faktyczny

**To nie jest jeszcze ukończony importer.** Wykonanie zgodnie z wymaganiem
zatrzymano, gdy oryginalne walidatory wykryły brak wymaganych informacji.
Tryb `--import` istnieje, ale pozostaje bezpiecznie zablokowany; nie ma
zaimplementowanej, przetestowanej ścieżki zapisu ani obietnicy idempotencji.
Nie uruchamia on zapisu po nieudanym dry-run.

Źródłowa instytucja wybranego małego zbioru nie podaje faksu i skrótu, których
model wymaga podczas `full_clean()`. Model zasobu wymaga również niepustego
`old_resource_type`, którego obecny publiczny dokument nie zawiera.
Nie wyłączono walidatorów i nie wymyślono wartości zastępczych.

Przed dalszym etapem potrzebne jest uzgodnienie, jak legalnie odwzorować brakujące
pola, ewentualnie jawna zgoda na odstępstwo od wymogu pełnej oryginalnej walidacji.
Nie oznacza to automatycznej konieczności zmiany schematu, ale takiego odstępstwa
nie przyjęto bez zgody.

Raporty są w `reports/aed_import_report.json` i `.md`; źródłowe publiczne metadane
w `reports/aed_discovery.json`. Nie ma manifestu utworzonych lokalnych ID, ponieważ
nie utworzono żadnego rekordu. Żadne urządzenie nie zostało uznane za zweryfikowane.
Nie wykonano testów pobierania importowanych plików, panelu ani powtórnego importu.

Istniejący ResourcesStorage ma włączone App Storage; sprawdzono dostęp do
zasobnika bez zapisu. Ograniczenia przyszłego bezpiecznego zapisu obejmują
atomowy manifest, wznowienie po awarii, kontrolę sygnałów zmiany linku i
publikacji, bezpieczne niepowtarzalne nazwy plików i weryfikację API.
