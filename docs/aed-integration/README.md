# MCOD ↔ AED Puls

Adapter używa rzeczywistych modeli MCOD `Dataset`, `Resource`, `ResourceFile`
i istniejącego mechanizmu walidacji/publikacji. Nie tworzy użytkowników MCOD
ani ról ADMIN / USER / ORGANIZATIONS.

## Bieżący status

Kod uruchamia panel Django pod `/` i oryginalny Falcon pod `/api/`, za wspólnym
proxy. W środowisku roboczym używaj obecnego adresu HTTPS podglądu bez `:5000`.
To nie jest stabilny adres integracji między projektami.

**Właścicielka zatwierdziła osobną bazę produkcyjną z początkową kopią danych
development.** W Publishing wybierz kopiowanie aktualnych danych dev i opublikuj
aplikację. Dla istniejącej bazy produkcyjnej oznacza to zastąpienie jej zawartości;
baza dev pozostaje bez zmian. Późniejsze zapisy obu baz nie synchronizują się.
Zobacz [procedurę publikacji](shared-database.md).
Adres przydzielony przez Publishing nie dowodzi udanego startu. Po publikacji
używaj faktycznego adresu HTTPS aplikacji z końcówką `/api`.
Nie używaj `api.dane.gov.pl`: to inna instalacja, nie ten projekt.

## Uruchomienie lokalne na Replit

1. `bash scripts/replit/setup.sh` instaluje oryginalne zależności oraz SDK App Storage.
2. Workflow **Supporting services** uruchamia Redis, RabbitMQ i Elasticsearch.
3. Migracje development uruchamiaj wyłącznie po potwierdzeniu docelowej bazy:
   `bash scripts/replit/python.sh manage.py migrate`.
   Migracja adaptera została już zastosowana w bazie dev. Strukturą zarządzanej
   bazy produkcyjnej zajmuje się Publishing; nie uruchamiaj tam tego polecenia.
4. Workflow **Django admin** uruchamia wspólny launcher dev/prod: Daphne ASGI
   dla Django, Falcon/Gunicorn, Celery oraz proxy na 5000. Wspólna konfiguracja
   aplikacji jest w `mcod.settings.replit_common`; produkcja zachowuje swoje
   bezpieczne cookies, `DEBUG=False`, adres API i odrębną bazę.
5. Brakujące indeksy katalogu są odtwarzane w tle z istniejących rekordów.
   Nie usuwa to indeksów, użytkowników, zbiorów ani zasobów. Nieudane operacje
   inicjalizacji są logowane i ponawiane, bez blokowania serwera.
6. Build i startup nie uruchamiają testów ani własnych healthchecków, prób
   zapisu do App Storage lub kontroli gotowości usług. `ignorePorts=true`
   wyłącza kontrolę portów przy publikacji; inne kontrole platformy mogą pozostać.

## Konfiguracja wymagająca administratora

1. W Tools → App Storage utwórz prywatny zasobnik dla tego projektu. SDK używa
   domyślnego zasobnika przypisanego do projektu. Zweryfikuj:
   `bash scripts/replit/python.sh manage.py aed_storage_check`.
2. Dodaj `AED_INTEGRATION_SECRET` przez Replit Secrets. Użyj długiej losowej
   wartości i zapisz tę samą wartość jako sekret **backendu** AED Puls.
   Nigdy nie umieszczaj jej w przeglądarce, repozytorium ani adresie URL.
3. Po udanym sprawdzeniu App Storage włącz `MCOD_APP_STORAGE_ENABLED=true`
   i zrestartuj workflow. Produkcyjny skrypt wymaga App Storage i nie przyjmuje
   cichego zastępstwa plikami lokalnymi.
4. W panelu Django utwórz **AED organization mapping**: zewnętrzny identyfikator
   organizacji AED Puls → istniejąca instytucja MCOD. Wskaż kategorię DCAT
   (nie dawną kategorię bez kodu) i co najmniej jeden tag. Zapis instytucji i
   przypisania jest operacją administratora MCOD, nie publicznym endpointem.
5. Instytucja musi być opublikowana przed publikacją jej zbiorów.
6. Utwórz **AED national catalog**, wybierz mapowanie instytucji odpowiedzialnej
   za agregat oraz licencję. Nie ustawiaj `MAIN_DGA_DATASET_OWNER_ORGANIZATION_PK`.

Jeden klucz jest kluczem zaufanego backendu AED Puls i umożliwia mu operacje
we wszystkich włączonych mapowaniach. To nie jest klucz użytkownika ani klucz
pojedynczej organizacji. Backend AED Puls musi przed każdym wywołaniem sprawdzić
swoje uprawnienia użytkownika i wybrać właściwe `external_organization_id`.
Adapter odrzuca dostęp do nieprzypisanych instytucji i przypisanie zbioru należącego
do innej instytucji. Nie przyjmuje dowolnego `organization_id` przy tworzeniu.

## API

- Oryginalne API odczytu: `GET /institutions`, `/datasets`, `/resources`.
- Dokumentacja oryginalnego API: `/api/doc`; specyfikacja: `/api/spec/1.4`.
- Specyfikacja adaptera: `/api/integrations/aed/openapi.yaml`.
- Ścieżki w `openapi.yaml` są względne do `MCOD_API_BASE_URL`, czyli końcówki `/api`.
- Zapis wymaga `Authorization: Bearer <sekret>`, HTTPS oraz mapowania instytucji.
- Wewnętrzne porty Django/Falcon są dostępne tylko na loopback.
- Nie przekazuj nagłówków autoryzacji do zewnętrznych URL z metadanych.

| Metoda | Ścieżka względem `/api` | Działanie |
|---|---|---|
| GET | `/integrations/aed/v1/institutions` | Włączone mapowania instytucji |
| GET, POST | `/integrations/aed/v1/organizations/{org}/datasets` | Lista / tworzenie lub bezpieczne przypisanie zbioru |
| GET, PATCH | `/integrations/aed/v1/organizations/{org}/datasets/{dataset}` | Metadane, zasoby / edycja zbioru |
| POST | `/integrations/aed/v1/organizations/{org}/datasets/{dataset}/publish` | Publikacja zbioru |
| POST | `/integrations/aed/v1/organizations/{org}/datasets/{dataset}/resources` | Wysłanie CSV/XLSX |
| GET, PUT | `/integrations/aed/v1/organizations/{org}/resources/{id}` | Stan walidacji / wymiana pliku i metadanych |
| POST | `/integrations/aed/v1/organizations/{org}/resources/{id}/publish` | Publikacja po poprawnej walidacji |
| GET, POST | `/integrations/aed/v1/aggregate` | Stan / zlecenie agregacji |

## Kolejność publikacji

Utwórz lub przypisz zbiór, opublikuj zbiór, wyślij plik jako multipart,
odczytuj stan zasobu, opublikuj zasób dopiero po zakończonej walidacji.
`202 Accepted` oznacza przyjęcie pliku do walidacji, **nie opublikowanie**.
`409 validation_pending` wymaga ponowienia później; `422 validation_failed`
wymaga poprawienia danych. Zasób pozostaje szkicem.

Aktualizacja `PUT` zastępuje plik pod tym samym identyfikatorem MCOD i cofa zasób
do szkicu. Ponownie sprawdź walidację i wywołaj publikację. Pola `title`,
`external_dataset_id`, `file` są wymagane; `description` i `source_url` opcjonalne.
`source_url` jest metadanym źródła; pliki są walidowane z przesłanej zawartości,
nie pobierane z tego URL.

## Schemat AED i agregacja

Wymagane kolumny CSV/XLSX:
`device_id,name,latitude,longitude,availability,hours,status,updated_at,
responsible_institution,source_dataset_id,source_url,license,verification_status`.

Opcjonalne: `description,address,city,verification_evidence_url`.
Identyfikatory zasobów MCOD są dodawane przez agregator, nie należy ich zgadywać
przy pierwszym wysłaniu. CSV: UTF-8 lub Windows-1250, separator wykrywany
automatycznie; XLSX: pierwszy arkusz, nagłówki w pierwszym wierszu. Limit: 25 MiB,
50 000 wierszy na źródło.

- `source_dataset_id` musi odpowiadać mapowaniu z URL żądania.
- Współrzędne muszą być skończone i w zakresach ±90 / ±180.
- Wymagane wartości nie mogą być puste; daty są normalizowane do UTC.
- Status: `available`, `unavailable`, `maintenance`, `unknown`;
  `active` / `operational` normalizują się do `available`.
- `verification_status`: wyłącznie `unverified` lub `source_reported`.
  To nie jest potwierdzenie fizycznego sprawdzenia AED.
- Licencje są nazwami licencji obsługiwanych przez MCOD i muszą odpowiadać
  licencji zbioru źródłowego.
- Powtórzone ID w jednym pliku są odrzucane. To samo ID w różnych źródłach
  łączy się w jeden rekord: najnowsze wartości i pochodzenie ze wszystkich źródeł.
- Różne ID z podobną lokalizacją i nazwą są oznaczane jako potencjalne duplikaty,
  nie usuwane automatycznie. To heurystyka, nie dowód, że to jedno urządzenie.
- Agregator zachowuje URL, instytucje, ID zbiorów/zasobów i licencje.
- Obecna konserwatywna polityka wymaga jednej zgodnej licencji źródeł i agregatu.
  Przy mieszanych licencjach agregacja zgłasza błąd zamiast samodzielnie
  zmieniać warunki udostępnienia.

Publikacja źródła zleca agregację w Celery. Agregat jest prawdziwym zasobem MCOD,
przechodzi istniejącą walidację; poprzedni zasób zbiorczy jest zachowywany jako
szkic. Ostatnia poprawna publikacja pozostaje dostępna w razie błędu kolejnej
agregacji; zawsze sprawdzaj `status`, `last_run_at` i `last_error`.

## Pliki i bezpieczeństwo

Zasobnik jest prywatny. Publiczne pliki zasobów są pobierane przez MCOD dopiero,
gdy zasób i jego zbiór są opublikowane. Administracyjny dostęp do szkiców wymaga
logowania i uprawnień MCOD. Lokalna kopia plików służy istniejącym walidatorom
wymagającym ścieżek; brakujący plik jest odtwarzany z App Storage.
Adapter nie przenosi automatycznie starych lokalnych plików do zasobnika.

## Publikacja na Replit

Konfiguracja publikacji: stale działająca VM z uwagi na Celery i usługi pomocnicze,
`bash scripts/replit/build.sh` oraz `bash scripts/replit/run-production.sh`.
Skrypt produkcyjny nie uruchamia migracji bazy. Standardowy Publish zarządza
schematem **osobnej** bazy produkcyjnej; nie podłącza obecnej bazy development.
Właścicielka zatwierdziła początkową kopię dev do osobnej bazy produkcyjnej.
Opcję kopiowania wybierz w Publishing; szczegóły i historyczne ograniczenia
wariantu wspólnej bazy opisuje [shared-database.md](shared-database.md).

Redis/RabbitMQ/Elasticsearch są tutaj usługami lokalnymi VM, a PostgreSQL
i pliki źródłowe są trwałe. Po ponownej publikacji brakujące indeksy odtwarzają
się z PostgreSQL; kolejki lokalnego brokera nie są trwałą ewidencją zadań.
Po przerwanym wdrożeniu ponowienie agregacji i publikacji wymaga świadomej decyzji.
Przygotowany wariant hackathonowy nie jest konfiguracją wysokiej dostępności
ani gotowym bezpiecznym wdrożeniem produkcyjnym na wspieranych komponentach.

Sekret i zasobnik są skonfigurowane. Test z rzeczywistym workerem potwierdził
publikację 3+2 rekordów, aktualizację agregatu i pobranie CSV przez publiczne API.
Wynik testu development nie potwierdza działania opublikowanej aplikacji.
W Publishing wybierz zatwierdzoną kopię danych i sprawdź dostęp oraz ustawienia
publikacji. Kliknięcie Publish należy do właścicielki projektu.

Po nadaniu rzeczywistego adresu produkcji:

1. W projekcie MCOD ustaw produkcyjny `API_URL` na pełny publiczny adres HTTPS z końcówką
   `/api` i opublikuj ponownie, aby procesy wczytały tę wartość. Jeżeli adres
   jest już znany w Publishing przed pierwszą publikacją, ustaw ją od razu.
   Bez prawidłowego adresu adapter odrzuca przesyłanie plików kodem
   `public_api_url_missing` zamiast utrwalać nieprawidłowe linki.
2. W backendzie AED Puls ustaw `MCOD_API_BASE_URL` na ten sam adres oraz
   `MCOD_INTEGRATION_SECRET` na ten sam sekret, który zapisano tutaj jako
   `AED_INTEGRATION_SECRET`. Nie umieszczaj sekretu w przeglądarce.
3. Utwórz w panelu MCOD zatwierdzone mapowania instytucji i wybierz właściciela
   oraz licencję agregatu. Test nie pozostawia syntetycznych instytucji w
   katalogu developerskim ani produkcyjnym.
4. Wykonaj test z osobnego backendu AED Puls pod adresem produkcyjnym.
   Ten test pozostaje niewykonany, dopóki projekt nie jest opublikowany.

Zobacz [examples.md](examples.md), [client.ts](client.ts),
[env.example](env.example) i [test-results.md](test-results.md).
