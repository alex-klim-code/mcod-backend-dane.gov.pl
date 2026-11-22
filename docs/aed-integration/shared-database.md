# Jedna baza dla development i publikacji — wynik weryfikacji

## Decyzja i status

Właścicielka wybrała **jedną obecną bazę PostgreSQL**, a nie kopiowanie danych do
osobnej bazy. Tego wyboru nie zastąpiono innym wariantem.

**Weryfikacja 2026-11-22: obecny, udokumentowany mechanizm Replit Publishing nie
udostępnia obsługiwanego powiązania publikacji z obecną zarządzaną bazą
deweloperską. Konfigurację zatrzymano przed podłączeniem publicznego środowiska.**

Źródła oficjalne, sprawdzone w pełnej treści, nie tylko w podsumowaniu wyszukiwania:

- [Development and production databases](https://docs.replit.com/features/data-and-storage/development-and-production):
  Publishing tworzy oddzielną bazę produkcyjną; obie zmienne `DATABASE_URL`
  mają tę samą nazwę, ale wskazują inne bazy. Na obecnej infrastrukturze baza
  produkcyjna jest tworzona automatycznie przy publikacji, jeśli development
  zawiera dane.
- [Fix a published app using a shared database](https://docs.replit.com/features/data-and-storage/shared-database-migration):
  współdzielenie dawnej bazy Neon jest konfiguracją historyczną, wycofywaną,
  a nie sposobem konfiguracji nowej publikacji.
- [Connection details](https://docs.replit.com/features/data-and-storage/connection-details):
  dostęp do obecnej bazy deweloperskiej jest ograniczony do kontekstu aplikacji.
  Identyczne adresy połączeń w różnych projektach nie dowodzą wspólnej bazy.

Opcja **Set up your production database with your current development data**
oznacza **kopię do osobnej bazy**, nie współdzielenie. Nie włączono jej.
Nie przenoszono ani nie nadpisywano `DATABASE_URL`, nie tworzono bazy zastępczej.

Odczyt metadanych publikacji zwrócił: **brak aktywnej publikacji**, brak publicznego
adresu, brak udanego buildu produkcyjnego. W repozytorium pozostaje przygotowana
konfiguracja VM, ale nie jest dowodem wdrożenia ani podłączenia bazy.
Nie mamy bezpośredniego wglądu w niewysłane wybory formularza Publishing ani listę
punktów odzyskiwania w interfejsie właścicielki.

## Co sprawdzono bez zmiany danych

Oba moduły ustawień (`mcod.settings.replit`, `mcod.settings.production_replit`)
czytają zarządzane `DATABASE_URL`. Produkcja zachowuje `DEBUG=False`,
HTTPS-only cookies i własne ustawienia CSRF; development ma inne zasady cookies.
Nie zmieniono połączeń ani ustawień bezpieczeństwa.

Kontrola `SELECT` w dostępnej bazie środowiska roboczego zwróciła wyłącznie liczniki:

| Kategoria | Liczba |
|---|---:|
| Użytkownicy MCOD | 1 |
| Instytucje | 0 |
| Zbiory | 0 |
| Zasoby | 0 |
| Pliki zasobów | 0 |
| Wpisy historii audytu MCOD | 3 |
| Wpisy audytu adaptera AED | 0 |
| Stany agregatu AED | 0 |
| Zastosowane migracje | 693 |

To stan bazy dostępnej w tym środowisku zadania, **nie dowód stanu bazy projektu
źródłowego ani zachowania jego wszystkich historycznych rekordów**. Nie było
wcześniejszego zestawienia do porównania. Nie wyświetlano rekordów użytkowników,
identyfikatorów połączenia ani wartości sekretów. Nie ma działającego środowiska
produkcyjnego, więc nie wykonano porównania fizycznej tożsamości obu baz.
Nie należy uznawać samych równych liczników za dowód takiej tożsamości.

Przegląd skryptów `build.sh`, `setup.sh`, `start.sh` i `run-production.sh`
nie wykazał automatycznych migracji, resetowania bazy ani ładowania danych.
Build zbiera pliki statyczne, start może tworzyć i zapełniać brakujące indeksy
Elasticsearch. **Nie uruchamiano buildu, procesów produkcyjnych, migracji ani
testów zapisujących do dostępnej bazy** w ramach tej weryfikacji.
Kontrola `git diff --check` i składni Bash czterech wymienionych skryptów
zakończyła się poprawnie. Podgląd `/login/` na porcie 5000 nie był uruchomiony
(odmowa połączenia); nie potwierdzono interfejsu ani pracy usług w tej sesji.
Nie uruchamiano ich tylko na potrzeby dokumentacyjnej weryfikacji.

## Odtwarzanie i klucze — warunki przed jakimkolwiek publicznym podłączeniem

Nie potwierdzono istnienia aktualnej kopii ani konkretnego punktu przywracania:
dostępne narzędzia nie pokazują listy kopii. Nie deklarujemy, że dane mają
zweryfikowaną kopię zapasową.

- Dla obecnej bazy deweloperskiej właścicielka powinna sprawdzić checkpoint
  sprzed zmian i dostępność opcji przywrócenia **bazy**, nie tylko kodu.
  Snapshot bazy jest wykonywany w trybie best-effort; checkpoint kodu nie daje
  gwarancji snapshotu danych.
- Przy odtwarzaniu wybrać checkpoint z poprawnymi danymi i przywracanie bazy.
  Wszystkie późniejsze zapisy zostaną cofnięte; najpierw wstrzymać zapis i workery.
  Nie wykonano odtwarzania.
- Dla ewentualnej przyszłej osobnej bazy produkcyjnej mechanizm jest inny:
  Database → Production → Settings → Advanced → Point-in-time recovery /
  Scheduled backups. Nie jest to ochrona obecnej bazy deweloperskiej.
- Szczegóły: [Data recovery](https://docs.replit.com/features/data-and-storage/data-recovery).

Potwierdzono wyłącznie obecność wspólnego `SESSION_SECRET` i
`AED_INTEGRATION_SECRET`; nie odczytywano ich wartości. Nie ma osobnego sekretu
`FIELD_ENCRYPTION_KEYS`. Oba moduły używają wtedy tego samego sposobu wyprowadzania
klucza pól z `SESSION_SECRET`. **Nie zmieniać tego sekretu ani sposobu wyprowadzania
klucza**: istniejące zaszyfrowane pola mogłyby przestać się odczytywać.
Nie dodawać nowego losowego klucza jako zastępstwa dla dotychczasowego.
Sama obecność sekretu nie dowodzi zgodności kluczy z nieuruchomioną publikacją.

## Konsekwencje jednej bazy, gdyby wariant stał się oficjalnie dostępny

- Każdy zapis, usunięcie i migracja z dowolnego środowiska zmieniałyby te same
  dane. Development nie byłby miejscem do eksperymentów na danych rzeczywistych.
  Nie uruchamiać `flush`, ładowania fixtures, resetów ani próbnych publikacji.
  Migracje wymagają uzgodnionego okna, wstrzymania zapisów/workera w obu
  środowiskach, sprawdzonego odtwarzania i zgodności obu wersji kodu.
- Testy wymagają **odrębnej bazy testowej**, oddzielnych indeksów (także danych
  tabelarycznych), brokera/kolejek i izolacji plików. Rollback transakcji nie
  izoluje callbacków `on_commit`, Celery ani zewnętrznych zapisów.
- Sesje są w lokalnym cache Redis, nie w PostgreSQL. Wspólna baza i klucz podpisu
  nie zapewniają wspólnych sesji. Logowanie i wylogowanie w jednym środowisku
  nie synchronizuje automatycznie drugiego; nie współdzielić cookies między
  domenami w celu obejścia tej separacji.
- Callbacki po zapisie wysyłają zadania do brokera środowiska, które obsłużyło
  zapis. Drugi broker i worker nie dostają automatycznie tych samych zdarzeń.
  Lokalne kolejki nie są trwałą ewidencją zadań; po utracie VM zadanie może zniknąć.
- Lokalne indeksy Elasticsearch pozostają oddzielne. Zapis w development może
  nie pojawić się w produkcyjnym wyszukiwaniu. `aed_prepare_search` odtwarza
  brakujące indeksy, ale nie naprawia stale istniejących indeksów w drugim
  środowisku. Jest to bloker równoległej pracy zapisującej, nie rozwiązana funkcja.
- Wspólny PostgreSQL nie udostępnia plików z dysku drugiej VM. Adapter wymaga
  tego samego zatwierdzonego prywatnego zasobnika i dostępu w obu środowiskach;
  historyczne lokalne pliki nie są automatycznie przenoszone do App Storage.
  Trzeba osobno potwierdzić ich dostępność bez modyfikowania rekordów.
- AED Puls nadal jest właścicielem swoich użytkowników i ról. MCOD zachowuje
  mapowania instytucji oraz historię zasobów/agregatu, bez synchronizacji kont
  i bez usuwania poprzednich publikacji.

## Co dalej w Publishing

**Nie publikować w przekonaniu, że przygotowane skrypty dają jedną bazę.**
Nie wybierać kopii danych jako zastępstwa dla decyzji właścicielki.
Brakuje obsługiwanego powiązania platformy; nie rozwiązuje się tego zmianą nazwy
zmiennej, jej ręcznym nadpisaniem ani przekazaniem zarządzanego adresu.
Jeśli Replit udostępni taki wariant, najpierw potwierdzić go w aktualnej
dokumentacji i Database / Publishing, następnie zweryfikować punkt odzyskiwania
i rozwiązać wyżej opisane blokery indeksów, kolejek i plików.

Dopiero po usunięciu blokerów właścicielka wybiera region i dostęp w Publishing;
region jest ustalany przy pierwszej publikacji. Ten dokument nie upoważnia
do publikacji. Python 3.8, Django 2.2 i Elasticsearch 6.8 są niewspierane;
obecnego stosu nie uznajemy za gotowy do bezpiecznej produkcji.

Po ewentualnej zatwierdzonej publikacji:

1. Pobrać faktycznie przydzielony adres z Publishing. Ustawić w MCOD `API_URL`
   na ten adres HTTPS z `/api`; w AED Puls ten sam `MCOD_API_BASE_URL`.
   Nie używać adresu preview ani adresu innej instalacji.
2. Przed testami zapisu wykonać wyłącznie odczyty: `/api/ping`,
   `/api/institutions`, `/api/datasets`, `/api/resources` oraz odczyty adaptera
   z uprawnionego backendu. Nie tworzyć danych syntetycznych.
3. Przy oficjalnie obsługiwanym współdzieleniu porównać z obu rzeczywistych
   runtime'ów potwierdzoną przez platformę tożsamość bazy i liczniki/historię
   w transakcjach tylko do odczytu, bez logowania połączeń ani danych osobowych.
   Odczyt repliki produkcyjnej sam w sobie nie dowodzi wspólnego serwera.
4. Sprawdzić odczyt istniejących publicznych plików i świeżość indeksów;
   endpointy list używające Elasticsearch nie dowodzą kompletności PostgreSQL.

Wszystkie kontrole po publikacji, porównanie obu połączeń i test z backendu
AED Puls **pozostają niewykonane**. Nie ma publicznego `MCOD_API_BASE_URL`.
