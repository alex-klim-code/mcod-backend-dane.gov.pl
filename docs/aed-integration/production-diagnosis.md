# Development vs Production: diagnoza braku backendu 8001

Stan rozpoznania: 2026-11-22. To raport diagnostyczny, nie potwierdzenie naprawy.

## Aktualizacja: diagnostyka rzeczywistego startu admina

Użytkownik potwierdził zmianę Production na 8 GiB / 1 vCPU. Nie zmieniono
zasobów ani portów. Poniższy starszy odczyt 2 GiB dotyczy poprzedniej publikacji,
nie obecnego przydziału maszyny.

Nowsze dostępne logi bez identyfikatora rewizji pokazują:

- 04:45:18.618 UTC: `starting up user application`;
- 04:45:29.186 UTC: Gunicorn nasłuchuje na 8000;
- 04:45:24.097–04:46:59.215 UTC: 79 odmów połączenia Nginx do 8001.

Nie ma wpisów potwierdzających wywołanie admina, jego zakończenie lub traceback.
Bieżący wykaz buildów zwrócił pustą listę; historyczna rewizja poniżej nie była
już dostępna. Tych logów nie można uczciwie przypisać do konkretnego SHA obrazu.
Nadal nie ma dostępu do konsoli/procesów/plików VM. Nie ustalono przyczyny
nieobecności admina na Production.

### Co zapisuje teraz launcher

Kod źródłowy nie zawiera warunku wyłączającego Daphne na produkcji:
`run-production.sh` → `start.sh` → `run-admin.sh` →
`python.sh -u scripts/replit/admin_server.py --bind 127.0.0.1 --port 8001 mcod.asgi:application`.
Wywołanie admina następuje po ewentualnym `collectstatic`.

Po opublikowaniu tych zmian deployment powinien wypisać:

1. `[mcod-launcher] event=start` oraz początek/koniec `collectstatic`, jeżeli wymagane;
2. `admin_supervisor_spawn` i PID nadzorcy;
3. `[mcod-admin-launcher] event=runtime_file ... exists=true/false` dla interpretera,
   katalogu Daphne, `daphne/cli.py` i `admin_server.py` w wybranym runtime;
4. `before_spawn` z adresem i portem, a potem `process_spawned` z PID procesu;
5. `[mcod-admin] event=entrypoint_enter` — pierwszy dowód wykonania pliku Pythona;
6. JSON z `daphne_cli_import_begin/complete` i ścieżką rzeczywiście zaimportowanego Daphne;
7. `production_settings_import_begin/complete`, `django_setup_begin/complete`
   i `asgi_routing_import_begin/complete`;
8. JSON `stage=listening, host=127.0.0.1, port=8001` dopiero z rzeczywistego
   callbacku otwarcia socketu Twisted/Daphne, nie na podstawie istnienia PID;
9. po zakończeniu procesu: `process_exit`, PID i rzeczywisty `exit_code`,
   a dla statusu sygnałowego także numer sygnału.

Import ustawień może wystąpić przed wejściem do `mcod.asgi`: pakiet `mcod`
inicjalizuje także Celery. Kolejność komunikatów odzwierciedla prawdziwe importy.

Przedłużony start wypisuje stosy Pythona co 45 sekund. To diagnostyka, nie limit
czasu startu: nie zabija procesu i nie zwraca HTTP 200. Stos pozwala odróżnić
import modułu, ładowanie ustawień i oczekiwanie w połączeniu z bazą. Timer jest
anulowany po otwarciu socketu lub zakończeniu inicjalizacji. Wyjątki mają traceback
i ostatni etap (`last_stage`), bez zrzutu środowiska, lokalnych zmiennych lub DSN.
Oba strumienie procesu trafiają bezpośrednio do stderr deploymentu; nie ma
przekierowania do niewidocznego pliku ani potoku zmieniającego kod wyjścia.

Daphne 2.5 potrafi zakończyć `run()` bez wyjątku po błędzie bindowania. Wrapper
zachowuje traceback tego błędu i zwraca wtedy niezerowy status zamiast fałszywego
sukcesu. Nie zmienia to wybranego adresu ani portu.

### Wyniki lokalne a Production

Siedem izolowanych testów sprawdziło oba strumienie, PID, statusy 0/23/143,
nieudany import oraz rzeczywisty zrzut stosu zablokowanego importu.
Osobny lokalny start z pakowanym runtime i profilem `production_replit` przeszedł
import Daphne, ustawień, `django.setup()` i routingu. Celowo użyto zajętego portu
8001: `CannotListenError` miał pełny traceback i status 1. To kontrolowany test
raportowania błędu, NIE wyjątek znaleziony na Production ani test produkcyjnej bazy.
Nie uruchomiono publikacji; do dowodu wykonania na VM potrzebne są nowe logi po
wdrożeniu tych plików.

### Końcowa weryfikacja dostępności

- Wszystkie 12 testów diagnostyki i istniejącej konfiguracji publikowania przeszło.
- Development: callback Daphne potwierdził PID 39464, `127.0.0.1:8001`,
  05:01:06.797 UTC. `/` i `/login/` przez publiczny proxy Development zwracają
  HTTP 200 z rzeczywistym formularzem logowania MCOD. Bezpośrednie `/login/` na
  8001 również sprawdzono podczas tej sesji.
- Metadane publikacji zmieniły status na sukces: build
  `0557b566-a958-4c7e-9f46-4d896961e9cd`, zakończenie około 04:57:56 UTC.
- Po tej zmianie niezależne żądania HTTPS spoza powłoki workspace do
  `https://mcod-backend-danegovpl.replit.app/` i `/login/` zwróciły HTTP 200
  z formularzem zawierającym token CSRF i pole hasła. To sprawdzenie rzeczywistej
  strony aplikacji, nie jedynie odpowiedzi Gunicorna ani statycznego healthchecka.
- Nie potwierdzono uruchomienia nowych znaczników diagnostycznych w tym obrazie VM.
  Publiczna dostępność wróciła podczas pracy, bez zainicjowania publikacji przez
  agenta. Nie należy przypisywać tego powrotu nowemu kodowi ani uznawać poprzedniej
  przyczyny 502 za wyjaśnioną.

Podczas kontroli Development wykryto też drugie kopie workflow konkurujące
o zajęte porty. Zatrzymano wyłącznie rozpoznane stare grupy procesów Development
i przywrócono te same usługi oraz aplikację pod tymi samymi portami. Nie zmieniono
konfiguracji ani stanu usług Production. Oba workflow Development ponownie działają.

## Osobna poprawka: formularz nie wysyłał danych do logowania

HTTP 200 formularza potwierdza dostępność strony, ale nie poprawność logowania.
Późniejsza kontrola Production wykazała pusty `action` formularza. Na stronie
głównej przeglądarka wysyłała więc `POST /`, a proxy zamieniało odpowiedź
przekierowującą backendu w wewnętrzny GET formularza, gubiąc jego treść.
Puste kontrolowane POST-y bez danych logowania potwierdziły różnicę:
root zwracał formularz bez walidacji, a `/login/` pokazywał błędy wymaganych pól.

Formularz ma teraz jawny adres nazwanej trasy logowania. Dla starych formularzy
`POST /` zwraca względne `307 /login/`, zachowując metodę i treść bez zmiany
originu HTTPS lub ujawniania wewnętrznego portu. Nie wyłączono CSRF ani Axes.
Przeszło siedem testów konfiguracji publikowania, w tym nowe regresje.
Rzeczywisty test Development potwierdził adres formularza, przekierowanie 307
i walidację Django z zaakceptowanym tokenem CSRF.

Odczyt Production potwierdził też brak dwóch wskazanych kont testowych.
Nie utworzono ich ani nie zmieniono istniejących haseł. Konta i zmiany haseł
z workspace Shell nie synchronizują się do osobnej bazy Production.
Do czasu publikacji poprawki można omijać błąd formularza strony głównej,
wchodząc bezpośrednio na `/login/`.

## Historyczne dowody z poprzedniej publikacji

Nieudana rewizja: `3c2f1a6a-6692-4032-a192-0c5ef14a4cb4`.
Utworzona 03:53:52 UTC, zakończona niepowodzeniem 04:04:10 UTC.

- 04:00:48 UTC: Gunicorn nasłuchuje na `127.0.0.1:8000`.
- 04:01:10 UTC: Nginx:
  `connect() failed (111: Connection refused) while connecting to upstream`,
  `upstream: "http://127.0.0.1:8001/"`, `host: "127.0.0.1:1104"`.
- Odmowa połączenia z 8001 powtarza się do 04:03:47 UTC.
- Brakuje wpisu potwierdzającego gotowość admina, jego tracebacku i kodu wyjścia.
- Przeszukano logi rewizji również bez filtra poziomu ważności.

Potwierdzony jest niedostępny upstream 8001, nie przyczyna jego niedostępności.
Nie ma dowodu pozwalającego wskazać OOM, brak Daphne lub wadę MCOD.
Port 1104 występuje w kontekście przekierowania platformy/Host; nie jest
dowodem, że źródłowa konfiguracja Nginx nasłuchuje na 1104.

## Historyczne porównanie i granice dostępu

| Obszar | Development — potwierdzone w workspace | Production |
| --- | --- | --- |
| Komenda | Dwa workflow: `services.sh` i `start.sh` | W konfiguracji publikowania: `run-production.sh`, następnie `start.sh` |
| Python i pakiety | `.cache/python/.../python3.8`, `.pythonlibs/lib/python3.8/site-packages` | Wrapper wybiera `runtime/python/.../python3.8`, `runtime/site-packages`; nie odczytano plików faktycznej VM |
| Profil ustawień | `mcod.settings.replit`: DEBUG=True, AXES_ENABLED=False, cookies preview SameSite=None | `mcod.settings.production_replit`: DEBUG=False, SameSite=Lax, AXES dziedziczone z konfiguracji bazowej (domyślnie aktywne dla admina). To różnice źródeł, nie odczyt efektywnych ustawień uruchomionego procesu VM |
| Zmienne i sekrety | Skonfigurowane SESSION_SECRET, AED_INTEGRATION_SECRET i zarządzane DATABASE_URL | Te same nazwy są skonfigurowane jako dostępne; narzędzie nie ujawnia wartości ani nie dowodzi ich identyczności w historycznej rewizji. API_URL jest ustawiony osobno dla produkcji |
| Nginx | Źródło: `listen 0.0.0.0:5000`, proxy panelu do `127.0.0.1:8001`, API do 8000 | Log potwierdza docelowy upstream 8001; aktywnego pliku konfiguracji VM nie odczytano |
| Porty | TCP 5000, 8000, 8001, 6379, 5672 i 9200 przyjmują połączenia | Log potwierdza nasłuch 8000 i odmowę 8001; bez aktualnego odczytu listy socketów VM |
| `.replit` | VM, port 5000→80, `ignorePorts=false`; istnieje też mapowanie 25672→3001 | Nie ustalono zawartości `.replit` spakowanej do nieudanej rewizji. Dodatkowe mapowanie brokera nie wyjaśnia odmowy połączenia lokalnego 8001 |
| Pliki | Interpreter, `daphne/cli.py`, `django/__init__.py`, `admin_server.py`, `mcod/asgi.py` i podstawowy CSS istnieją. Porównane lokalne kopie dev i release interpretera/Daphne/Django mają zgodne SHA-256 | Nie sprawdzono ich obecności, praw ani hashy na produkcyjnej VM |
| RAM | Limit cgroup 8 GiB; odczyt licznika OOM wskazywał 0 | Metadane nieudanej rewizji: e2-small, 0,5 vCPU, 2 GiB. Logi nie potwierdzają zabicia admina przez OOM |
| Kolejność | Bieżący `start.sh`: opcjonalny start usług; collectstatic tylko przy braku pliku; uruchomienie admina, API, workera, inicjalizacji wyszukiwarki, Nginx; nadzór `wait -n` | Logi potwierdzają jedynie zdarzenia powyżej. Nie potwierdzono pełnej kolejności startu ani stanu PID admina |

Źródło `start.sh` i ustawień w workspace ma zmianę z 04:10:53 UTC, późniejszą
niż zakończenie nieudanej publikacji. Metadane buildu nie udostępniają SHA
źródeł. Dobór commita według czasu NIE potwierdza zawartości obrazu produkcyjnego.
Test profilu `production_replit` na maszynie Development również nie testuje
plików, limitów RAM, procesów i środowiska rzeczywistej VM.

## Polecenia do wykonania wyłącznie w rzeczywistym Production

Nie uruchamiaj ich w Shell Development jako zamiennika diagnostyki produkcji.
Jeżeli nie masz konsoli procesu Production, sam workspace nie da tych danych.
Blok jest samodzielny: nie wymaga obecności tego nowego dokumentu w starym obrazie.
Nie uruchamia nowych serwerów, nie restartuje usług, nie zapisuje do bazy i nie
wypisuje wartości zmiennych ani sekretów. Nie używaj `env`, `printenv`, `ps e`
ani odczytu `/proc/*/environ` do przesyłania wyników.

```bash
cd /home/runner/workspace || exit 1
date -u
python - <<'PY'
import hashlib
import os
from pathlib import Path
import socket

root = Path.cwd()
print("ROOT", root)
print("ENV_PRESENCE_CURRENT_SHELL_ONLY")
for key in ("SESSION_SECRET", "AED_INTEGRATION_SECRET", "DATABASE_URL",
            "DJANGO_SETTINGS_MODULE", "MCOD_RUNTIME_ROOT",
            "MCOD_START_SERVICES", "PURE_PYTHON"):
    print(key, "present" if key in os.environ else "absent")
# Launcher-only exports need not exist in an independent interactive shell.
print("CGROUP")
for name in ("memory.max", "memory.current", "memory.peak",
             "memory.events", "cpu.max"):
    p = Path("/sys/fs/cgroup") / name
    print(name, p.read_text().strip() if p.is_file() else "unavailable")
print("TCP_LOCAL")
for port in (1104, 5000, 8000, 8001, 6379, 5672, 9200):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            print(port, "accepts_connections")
    except OSError as exc:
        print(port, type(exc).__name__, "errno", exc.errno)
print("PROCESS_ROLES_NO_ARGUMENT_VALUES")
for proc in Path("/proc").iterdir():
    if not proc.name.isdigit():
        continue
    try:
        args = (proc / "cmdline").read_bytes().split(b"\0")
        if any(arg.endswith(b"/admin_server.py") for arg in args):
            print("admin", "pid", proc.name)
        elif b"gunicorn" in args:
            print("api_gunicorn", "pid", proc.name)
        elif b"celery" in args and b"worker" in args:
            print("celery_worker", "pid", proc.name)
    except OSError:
        pass  # A process can exit or be inaccessible during the snapshot.
print("FILES_AND_CODE_HASHES")
files = (
    "scripts/replit/start.sh", "scripts/replit/run-production.sh",
    "scripts/replit/python.sh", "scripts/replit/runtime-paths.sh",
    "scripts/replit/admin_server.py", "scripts/replit/nginx.conf",
    "mcod/asgi.py", "mcod/settings/replit_common.py",
    "mcod/settings/production_replit.py",
    "runtime/python/cpython-3.8.20-linux-x86_64-gnu/bin/python3.8",
    "runtime/site-packages/daphne/cli.py",
    "runtime/site-packages/django/__init__.py",
    "statics/admin/css/base.css",
)
for name in files:
    p = root / name
    if not p.is_file():
        print(name, "MISSING")
        continue
    try:
        digest = hashlib.sha256()
        with p.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        print(name, "exists", "executable", os.access(str(p), os.X_OK),
              "sha256", digest.hexdigest())
    except OSError as exc:
        print(name, "UNREADABLE", type(exc).__name__)
print("RENDERED_NGINX_DIRECTIVES")
p = Path("/tmp/mcod-nginx.conf")
if p.is_file():
    for line in p.read_text().splitlines():
        value = line.strip()
        if value.startswith("listen "):
            print(value)
        elif value.startswith("proxy_pass http://127.0.0.1:"):
            # Output only known local port targets; never arbitrary URLs.
            target = value.split("127.0.0.1:", 1)[1].split("/", 1)[0].rstrip(";")
            if target.isdigit():
                print("proxy_loopback_port", target)
else:
    print("expected_rendered_config_missing")
PY
# No command arguments or process environments: avoid accidental secret output.
ps -eo pid,ppid,stat,etime,rss,comm
```

RSS w `ps` jest w KiB. `memory.max` jest w bajtach; `max` oznacza brak limitu
na tym poziomie cgroup. Brak plików cgroup v2 nie oznacza braku limitu — potrzebny
jest wtedy odczyt wariantu cgroup v1 lub danych nadzorcy. Liczniki OOM dotyczą
życia kontenera i same nie identyfikują zabitego procesu.

## Brakujący dowód i dalszy krok

Do wskazania minimalnej poprawki potrzeba jednego z poniższych:

- potwierdzenia brakującego lub nieczytelnego pliku w obrazie VM;
- stderr procesu `admin_server.py` z błędem uruchamiania;
- potwierdzenia, że proces działa bez nasłuchu, wraz ze stosem startującego Pythona;
- zdarzenia nadzorcy zawierającego PID i kod wyjścia/sygnał admina.

Nie należy zmieniać 8001 na 1104 ani wyłączać usług na podstawie samego 502.
Nie zmieniono logiki MCOD, konfiguracji Nginx ani przydziału zasobów. Dodano
diagnostykę startu i niezerowy status przy błędzie bindowania. Nie uruchomiono
publikacji w ramach tego rozpoznania.

Gdy konsola Production jest niedostępna, logi z nowego bootstrapu podczas
następnego wdrożenia pozwolą zebrać PID admina, etapy importu, stos przy
przedłużonym starcie i kod wyjścia — bez wypisywania sekretów, zmiany portów,
wyłączania usług lub zastępowania odpowiedzi healthcheck.
