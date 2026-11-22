# Rzeczywiście wykonane sprawdzenia

Stan: 2026-11-22. To jest zapis wyników, nie deklaracja pełnej gotowości produkcyjnej.

## Przeszły

- Django system check: bez błędów.
- Migracja adaptera `aed_integration`: zastosowana w bazie developerskiej.
- 19 testów regresyjnych adaptera w osobnej bazie testowej:
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
  - wymaganie pełnego adresu HTTPS dla linków plików;
  - wyłączenie połączeń RDF, gdy usługa jest wyłączona w konfiguracji;
  - dokumentacja Swagger używająca tego samego originu i specyfikacji AED.

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

## Rzeczywisty test end-to-end

Wynik: **1 passed**, osobno od 19 testów regresyjnych. W zwykłym uruchomieniu
ten test ma status `skipped`, ponieważ wymaga jawnego włączenia usług rzeczywistych.

```bash
RUN_AED_E2E=1 COMPONENT=api bash scripts/replit/python.sh -m pytest -q \
  --nomigrations -n0 --ds=mcod.settings.aed_e2e \
  mcod/aed_integration/tests/test_live_pipeline.py
```

Rzeczywiste PostgreSQL, Elasticsearch, prywatne App Storage i worker Celery
`solo`; izolowana kolejka pamięciowa zamiast brokera developerskiego.
Nie zastępowano wyników walidacji ani bramki publikacji.

Potwierdzono:

- Instytucje A i B, ich zbiory i źródła CSV zawierające 3 oraz 2 AED.
- Asynchroniczną walidację pliku, danych tabelarycznych i linku MCOD.
- Zapis plików do App Storage i odtworzenie identycznych bajtów po usunięciu
  lokalnej kopii.
- Publikację rzeczywistego zasobu zbiorczego z pięcioma rekordami.
- Aktualizację źródła i publikację nowej wersji agregatu.
- Pobranie metadanych i CSV przez oryginalne endpointy Falcon, wywołane
  klientem testowym WSGI.
- Zachowanie poprzedniego agregatu jako szkicu i odmowę jego anonimowego pobrania.
- Odrzucenie żądania bez tokenu oraz próby zmiany zasobu instytucji A przez
  ścieżkę instytucji B.
- Widoczność obu źródeł i nowego agregatu w oryginalnym panelu administratora:
  zalogowany klient testowy Django otrzymał HTTP 200 i linki do tych zasobów.
  Nie był to wizualny test zalogowanej przeglądarki.

Dane i konto administratora istniały tylko w testowej bazie. Test usuwa wyłącznie
własne obiekty App Storage oraz własne indeksy z unikalnym prefiksem.

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

## Konfiguracja i pozostałe kroki

- App Storage: zasobnik dostępny, trwały zapis włączony również w działającym
  procesie; rzeczywisty zapis i odczyt potwierdzono w teście end-to-end.
- Sekret integracji został zapisany przez bezpieczny formularz i wczytany po
  restarcie. Żądanie bez tokenu otrzymało 401 zamiast wcześniejszego 503.
  Nie ujawniano wartości sekretu.
- Projekt nie został opublikowany; brak produkcyjnego URL i testu z backendu
  AED Puls. Kod backendu AED Puls nie znajduje się w tym repozytorium.
- Skonfigurowano VM oraz polecenia budowania i uruchamiania dla Publishing.
  Po nadaniu adresu należy ustawić produkcyjne `API_URL` (HTTPS, końcówka `/api`)
  i wczytać je ponowną publikacją przed przesyłaniem plików.
- Do użycia rzeczywistych instytucji trzeba skonfigurować zatwierdzone mapowania
  oraz właściciela i licencję agregatu w panelu MCOD.

Wynik produkcyjny i test z osobnego projektu wymagają jeszcze publikacji.
