# Rzeczywiście wykonane sprawdzenia

Stan: 2026-11-22. To jest zapis wyników, nie deklaracja pełnej gotowości produkcyjnej.

## Przeszły

- Django system check: bez błędów.
- Migracja adaptera `aed_integration`: zastosowana w bazie developerskiej.
- 13 testów adaptera w osobnej bazie testowej:
  - poprawna normalizacja danych;
  - niepoprawne współrzędne / NaN;
  - odrzucenie niepotwierdzonej fizycznej weryfikacji;
  - niezgodny identyfikator zbioru źródłowego;
  - źródłowy URL bez HTTPS;
  - duplikat ID w jednym pliku;
  - brak autoryzacji / HTTPS;
  - utworzenie i publikacja zbioru, wysłanie multipart CSV;
  - odrzucenie dostępu i przypisania zbioru spoza instytucji;
  - odrzucenie pobrania szkicu i publikacji przy trwającej walidacji;
  - odrzucenie uszkodzonego XLSX;
  - odtworzenie lokalnego pliku z imitacji prywatnego zasobnika oraz odrzucenie
    zapisu, gdy zasobnik nie przyjmie pliku;
  - agregacja 3+2 rekordów z dwóch instytucji, wybór najnowszej wersji wspólnego
    ID, oznaczenie potencjalnych duplikatów, aktualizacja i zachowanie starego
    zasobu MCOD.

Polecenie:
```bash
COMPONENT=api bash scripts/replit/python.sh -m pytest -q --nomigrations -n0 \
  --ds=mcod.settings.test_replit mcod/aed_integration/tests
```

**Zakres:** testy używają lokalnej kolejki pamięciowej, nie brokera developerskiego.
Test agregatora korzysta z prawdziwych modeli i plików MCOD, ale
przejście asynchronicznych walidatorów zastępuje kontrolowaną odpowiedzią.
Nie jest dowodem działania całej kolejki Celery ani publikacji produkcyjnej.
`--nomigrations` tworzy izolowany schemat z modeli, ponieważ oryginalny łańcuch
migracji na czystej bazie odwołuje się do nieistniejącej tabeli
`counters_resourceviewcounter` przy tworzeniu materializowanego widoku.
Nowa migracja adaptera została osobno poprawnie sprawdzona na istniejącej bazie.

## Uruchomione

Django Admin, Falcon, Celery, Redis, RabbitMQ i Elasticsearch.
Utworzono brakujące indeksy katalogu bez usuwania istniejących danych.

Sprawdzone przez HTTPS w aktualnym podglądzie Replit z portem `:5000`:

| Ścieżka | HTTP |
|---|---|
| `/login/` | 200 |
| `/api/institutions` | 200 |
| `/api/datasets` | 200 |
| `/api/resources` | 200 |
| `/api/doc` | 200 |
| `/api/spec/1.4` | 200 |
| `/api/integrations/aed/openapi.yaml` | 200 |
| `/api/integrations/aed/v1/institutions` | 401 bez tokenu — sekret skonfigurowany, dostęp anonimowy odrzucony |

Celery odpowiedział `pong` na `inspect ping`: jeden worker online.
Stronę logowania sprawdzono wizualnie w świeżym Chromium. Style CSS działają.
Nie logowano się na istniejące konto i nie zmieniano jego hasła.
W developerskiej bazie po testach pozostaje 0 mapowań AED, 0 zbiorów i 0 zasobów.

## Niewykonane / wymagające konfiguracji

- App Storage: SDK zainstalowane; sprawdzenie domyślnego zasobnika nie przeszło.
  Należy utworzyć zasobnik w Tools → App Storage i ponowić sprawdzenie.
- Sekret integracji został zapisany przez bezpieczny formularz i wczytany po
  restarcie. Żądanie bez tokenu otrzymało 401 zamiast wcześniejszego 503.
  Nie ujawniano wartości sekretu.
- Nie wykonano pełnego testu 3+2 z rzeczywistym workerem walidującym pliki
  i pobraniem przez publiczne API.
- Nie potwierdzono widoku zalogowanego administratora dla testowych zasobów.
  Testowe rekordy były izolowane w bazie testowej.
- Projekt nie został opublikowany; brak produkcyjnego URL i testu z backendu
  AED Puls. Kod backendu AED Puls nie znajduje się w tym repozytorium.

Wynik należy uzupełnić po konfiguracji zasobnika, sekretu i rzeczywistych testach.
