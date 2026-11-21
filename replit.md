# Running the imported MCOD backend on Replit

## Scope

The existing Python/Django project and its `Pipfile.lock` are preserved. The
default preview runs the **Django administration component**, not the separate
public-facing dane.gov.pl frontend (which is not included in this repository).
This is a **development environment only**, not a production deployment.

## Run

Click **Run** to start the `Project` workflow. It starts:

- `Supporting services`: local Redis, RabbitMQ, and Elasticsearch 6.8.23, with
  the upstream Polish language resources and `analysis-stempel` / `analysis-icu`
  plugins. These services are private; only the web app is exposed.
- `Django admin`: the existing admin application on `0.0.0.0:5000`.

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
- No Celery workers, scheduled jobs, separate Falcon API, or Wagtail CMS server
  are started by the default workflow.

To run those existing components manually in a separate Shell:

```sh
# Falcon API (development only)
COMPONENT=api bash scripts/replit/python.sh -m gunicorn --bind 0.0.0.0:8000 mcod.api:app

# Wagtail CMS (development only)
COMPONENT=cms bash scripts/replit/python.sh manage.py runserver 0.0.0.0:8002

# Background tasks (only when you intend to process the queued jobs)
COMPONENT=celery bash scripts/replit/python.sh -m celery --app=mcod.celeryapp:app worker --pool=solo --concurrency=1 --loglevel=INFO
```

These optional components have not been verified end-to-end in this setup.
Background jobs require their own workers; starting RabbitMQ alone does not
process queued jobs. Search functionality needs indexes created using the
upstream `search_index` management command.

## Limits and safety

Python 3.8, Django 2.2, and Elasticsearch 6.8 are old, unsupported release lines.
Preserving them avoids an unrequested upgrade, but this setup must not be used
with sensitive or production data or published as-is. A supported-version upgrade
and security review are separate work.

Runtime downloads, packages, service data, and generated output are excluded from
Git and deployment packaging. PostgreSQL is persistent; local Redis/RabbitMQ/
Elasticsearch data under `.cache/services` is for development and can be lost if
the cache is removed. Do not use it as production storage.
