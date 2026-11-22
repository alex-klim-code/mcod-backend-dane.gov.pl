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
  one Celery worker.

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

- `mcod.settings.replit` is selected by the wrapper. Existing local and production
  settings are unchanged.
- The existing Replit `DATABASE_URL` provides PostgreSQL. Do not copy it into a file
  or log it. Existing upstream migrations were applied to the initially empty
  development database.
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

The workflow creates missing institution/dataset/resource search indexes
non-destructively and populates them from existing records. Full asynchronous
publication tests are documented separately in `docs/aed-integration/test-results.md`.

## AED Puls integration

See `docs/aed-integration/README.md` for the actual routes, the backend-only
TypeScript client, administrator-managed institution mappings and publication
sequence. AED Puls keeps its own users and roles; the adapter does not create
or synchronize them.

`AED_INTEGRATION_SECRET` belongs only in Replit Secrets. Without it the adapter
returns 503. Configure a private default App Storage bucket before enabling
`MCOD_APP_STORAGE_ENABLED=true`. Production startup requires that bucket and
the shared secret; no silent local-only file storage is allowed.

The prepared production scripts use `mcod.settings.production_replit` and
Gunicorn rather than Django's development server. They do not run schema
migrations against production; managed schema changes go through Publish.

Publishing builds Python, its locked packages, and Elasticsearch with its
plugins under `runtime/`. This is an intentional release dependency directory:
Git ignores it, but deployment packaging must include it. `.cache/` and
`.pythonlibs/` remain development-only and excluded from deployment packaging.
`scripts/replit/runtime-paths.sh` keeps production and development paths separate;
production startup fails immediately when the built runtime is missing.
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
