# Running the imported MCOD backend on Replit

## Scope

The existing Python/Django project and its `Pipfile.lock` are preserved. The
default preview runs the **Django administration component** and **Falcon API**, not the separate
public-facing dane.gov.pl frontend (which is not included in this repository).
This is a **development environment only**, not a production deployment.

## Run

Click **Run** to start the `Project` workflow. It starts:

- `Supporting services`: local Redis, RabbitMQ, and Elasticsearch 6.8.23, with
  the upstream Polish language resources and `analysis-stempel` / `analysis-icu`
  plugins. These services are private; only the web app is exposed.
- `Django admin`: Nginx on `0.0.0.0:5000`, routing `/api/` to Falcon on
  `127.0.0.1:8000` and the admin to Django on `127.0.0.1:8001`; also runs
  one Celery worker. Development and production use the same Daphne ASGI admin
  server (the server behind the former Channels runserver), Gunicorn API and
  shared `scripts/replit/start.sh` launcher.

The preview redirects to `/login/`. No administrator account or default password
has been created. Create your own account in the Replit Shell, where the password
is entered interactively:

```sh
bash scripts/replit/python.sh manage.py createsuperuser
```

Do not put passwords in chat, command arguments, or source files.

## Dependencies and commands

The project requires Python **3.8.20**, not the workspace's default Python 3.12.
`uv` restores this runtime under `.cache/python`; packages from the original lock
are installed under `.pythonlibs/lib/python3.8/site-packages`, without a virtualenv.
Always use the wrapper for project commands:

```sh
bash scripts/replit/python.sh manage.py check
bash scripts/replit/python.sh manage.py migrate --noinput
```

To restore dependencies after a fresh import or clearing caches:

```sh
bash scripts/replit/setup.sh
```

Start the supporting services before running Django commands. On a new, empty
development database, run `migrate --noinput` once. Startup deliberately does not
automatically migrate databases or load fixtures.

The original `init_mcod_db` command additionally loads upstream sample data.
It was **not** run here; no sample users or datasets were imported.

## Development configuration

- `mcod.settings.replit_common` contains the application settings used by both
  Replit profiles. Only environment identity, hosts, public API address and
  security/preview overrides belong in `replit` and `production_replit`.
- The existing Replit `DATABASE_URL` provides PostgreSQL. Do not copy it into a file
  or log it. Existing upstream migrations were applied to the initially empty
  development database.
- The locked PostgreSQL client predates TLS SNI. Both Replit settings profiles
  apply Neon's documented endpoint option for old libpq through
  `mcod.settings.database_compat`, deriving it from the current managed host.
  Keep TLS and credentials unchanged; do not hardcode a development endpoint into
  production or edit the managed connection string to work around this.
- The owner approved a **separate production database with an initial copy of
  development data**, superseding the earlier shared-database requirement.
  Use Publishing's data-copy option; do not copy or override managed credentials,
  reset development, or implement a custom production migration/copy script.
  Later changes in dev and production do not synchronize automatically. See
  `docs/aed-integration/shared-database.md` for the publishing procedure.
- Django signing and JWT signing use the workspace's `SESSION_SECRET`.
- If no `FIELD_ENCRYPTION_KEYS` secret is provided, development field encryption
  uses an HMAC-derived key from `SESSION_SECRET`. **Keep that secret stable**:
  changing it would make encrypted development fields unreadable. To use an
  existing encrypted database, supply its original keys in Secrets before use.
- Email is saved in `generated-artifacts/mail`, not sent externally.
- The upstream remote feature-flag service, Discourse integration, and optional
  RDF service are disabled in this development configuration.
- Cookies are HTTPS-only and configured for the proxied preview. Use Replit's
  HTTPS preview rather than a direct HTTP browser URL.
- Falcon and a single Celery worker are started by the default workflow.
  No Wagtail CMS server or scheduled beat worker is started.

Do not start duplicate Falcon or Celery processes while the default workflow
is running. The optional CMS can be started separately:

```sh
# Wagtail CMS (development only)
COMPONENT=cms bash scripts/replit/python.sh manage.py runserver 0.0.0.0:8002
```

The workflow initializes missing institution/dataset/resource search indexes
non-destructively in the background and populates them from existing records.
Failed initialization operations are logged and retried without blocking web
startup; this is real setup work, not a service-health probe. Full asynchronous
publication tests are documented separately in `docs/aed-integration/test-results.md`.

## AED Puls integration

See `docs/aed-integration/README.md` for the actual routes, the backend-only
TypeScript client, administrator-managed institution mappings and publication
sequence. AED Puls keeps its own users and roles; the adapter does not create
or synchronize them.

`AED_INTEGRATION_SECRET` belongs only in Replit Secrets. Without it the adapter
returns 503. Configure a private default App Storage bucket before enabling
`MCOD_APP_STORAGE_ENABLED=true`. Production startup requires that bucket and
the shared secret; no silent local-only file storage is allowed. There is no
automatic storage write/read preflight during startup.

The production entrypoint selects `mcod.settings.production_replit` and the
packaged runtime, starts supporting services, then delegates to the same
application launcher as development. Both profiles import the shared application
configuration; production retains `DEBUG=False`, secure cookies and its managed
production database. Neither launcher runs Django's development-server checks.
They do not run schema
migrations against production; standard Publish manages a separate production
schema, not a shared development connection. The owner must choose the approved
development-data copy in Publishing and click Publish. Do not describe the
production copy or hosted startup as completed before verification.

The owner requested explicit Daphne startup diagnostics for the missing admin
listener on 8001. `run-admin.sh` preserves stdout/stderr, the actual Python PID,
exit status and signal forwarding. The Python bootstrap logs import stages and
uses a native traceback timer while starting; only Daphne's successful socket
callback confirms listening and cancels that timer. These diagnostics do not
gate startup, replace HTTP responses or declare the deployment healthy.
See `docs/aed-integration/production-diagnosis.md`. Do not mistake local
production-profile results for execution in the deployed image.

Development and production databases, sessions, queues and search indexes are
independent. Tests must use a separate test database, broker, search namespaces
and isolated files, never the production database. Keep encryption/signing
secrets stable so copied encrypted fields remain readable. Existing App Storage
files are referenced by the copied records, not copied by PostgreSQL's data-copy
step; both environments need access to the configured private bucket.

Publishing builds Python, its locked packages, and Elasticsearch with its
plugins under `runtime/`. This is an intentional release dependency directory:
Git ignores it, but deployment packaging must include it. `.cache/` and
`.pythonlibs/` remain development-only and excluded from deployment packaging.
`scripts/replit/runtime-paths.sh` keeps production and development paths separate.
Missing binaries fail when executed; there is no build-marker preflight.
The Python wrapper enforces `PURE_PYTHON=1` to use zope.interface's supported
Python implementation: its optional C accelerator segfaulted during full Django
initialization even though isolated module imports passed. Keep the workaround
for build and runtime together. `PYTHONFAULTHANDLER=1` preserves native-crash
tracebacks; a passing lightweight import is not a substitute for the full build.
**Owner requirement for deployment diagnosis:** first establish a cause from
actual production-revision logs or configuration, then make only the minimal
supported correction. Do not guess or change MCOD logic or disable services
without justification. Compare launch commands, environment/secret presence
(never values), Nginx, backend port 8001, `.replit`, packaged files, RAM limits
and process order. A successful production-settings test inside development is
not verification of the deployed VM. If production process/filesystem access is
unavailable, state the limitation and provide commands for the actual production
environment rather than claiming those checks were performed there.

**Owner requirement:** dev and prod must use the same application features,
services, UI and shared launchers. Do not create a separate reduced production
backend. Environment-specific secrets, domains, secure cookies and the previously
approved independent production database remain separate.
Host validation is shared too: preview, published Replit hosts and loopback
hosts are allowed in both environments. Internal HTTP requests must not fail
solely because production forgot a loopback host supported in development.
Do not run tests, application health probes or custom
preflight checks during publishing or startup. Build installs dependencies and
collects static assets only; startup performs required setup and launches the
servers, worker and proxy. Keep package-integrity protections. The owner approved
platform HTTP-port detection as an exception: Reserved VM publishing must use
`ignorePorts=false` so public requests reach the application. Setting it true
can publish a background-only deployment that displays Replit's placeholder
instead of Django. Platform security/build validations may still run.
Verification commands, if needed, are manual and outside those lifecycle scripts.
The owner subsequently requested real integration verification and a proper
health endpoint. Run those checks manually, in isolated test infrastructure,
not as publishing/startup gates. `/health/` is process liveness;
`/health/ready/` checks PostgreSQL, Redis sessions, the three required catalog
indexes and the task broker, returning 503 if any is unavailable. It does not
claim a particular uploaded file is validated or that a worker finished it.
`MCOD_MINIMAL_MODE=true` (the default in the shared settings) disables RDF,
Discourse, Unleash and the periodic health-monitor thread in BOTH environments.
Setting it false restores their base configuration, but requires provisioning
their real services separately. Keep Elasticsearch, Redis, RabbitMQ and the
single Celery worker for the current unmodified MCOD publication pipeline.
Both launchers reuse the static assets prepared by the build instead of
reinitializing Django merely to collect them again on every restart. The shared
launcher collects them only if the required admin asset is absent, so a fresh
development checkout remains usable. After editing source static assets in
development, refresh them explicitly with `manage.py collectstatic`.
The shared Python wrapper sets `CELERY_SKIP_CHECKS=1`, and background catalog
initialization passes Django's `--skip-checks`; neither implicitly runs Django
system validation at startup. Static collection is build/setup work, not a test.

Only web port 5000 is mapped publicly, to external port 80. Redis, RabbitMQ,
Erlang distribution, and Elasticsearch must remain internal. The Python wrapper
uses the standard HTTPS preview origin without `:5000` for development API URLs.
The root proxy displays the existing login page with HTTP 200 for anonymous
requests so publishing can check readiness; other protected pages retain their
login redirects and authenticated dashboard responses pass through unchanged.

## Limits and safety

Python 3.8, Django 2.2, and Elasticsearch 6.8 are old, unsupported release lines.
Preserving them avoids an unrequested upgrade, but this setup must not be used
with sensitive or production data or published as-is. A supported-version upgrade
and security review are separate work.

Development caches, download archives, service data, and diagnostic output are
excluded from Git and deployment packaging. Required production binaries and
packages are rebuilt under the intentionally packaged `runtime/` directory.
PostgreSQL is persistent; local Redis/RabbitMQ/Elasticsearch state under
`.cache/services` can be lost when the cache is removed or the app is republished.
Do not treat that local state as durable production storage.
