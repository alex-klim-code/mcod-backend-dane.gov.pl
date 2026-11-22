# Development vs Production: diagnoza braku backendu 8001

Stan rozpoznania: 2026-11-22. To raport diagnostyczny, nie potwierdzenie naprawy.

## Dowody z rzeczywistej publikacji

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

## Porównanie i granice dostępu

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
Nie wprowadzono poprawki aplikacji, nie zmieniono jej konfiguracji i nie
uruchomiono publikacji w ramach tego rozpoznania.

Gdy konsola Production jest niedostępna, możliwy następny krok to zatwierdzony,
jednorazowy start diagnostyczny publikacji, rejestrujący PID admina, etapy importu,
stos przy przedłużonym starcie i kod wyjścia — bez wypisywania sekretów,
zmiany portów, wyłączania usług lub zastępowania odpowiedzi healthcheck.
