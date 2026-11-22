---
name: MCOD integration test isolation
description: Why database rollback alone does not isolate legacy MCOD integration tests.
---

Use an isolated database, broker and search namespace for MCOD integration
tests. Include the tabular-data index prefix, not only catalog index names.
Real storage tests must track and delete only the objects they created.

**Why:** Model callbacks can enqueue work even when a test later rolls back.
A live worker then receives IDs that do not exist in its database. The real
worker test also caught failures hidden by replacing the publication gate.

**How to apply:** Keep fast tests away from live workers and storage. Use an
opt-in real-worker test to prove validation, publication and downloads, rather
than treating mocked validation results as end-to-end evidence.

Use a fresh, uniquely named test database for runtime API verification, and
separate that verification from replaying the legacy migration history.

**Why:** Reusing older test schemas can collide with existing tables; replaying
the repository's historical SQL views in a fresh database can fail on their
cross-app dependencies before runtime tests execute. Neither proves a current
API failure. Functional tests can use real tables synchronized from the models
without certifying that historical migrations are correct.

**How to apply:** Use the isolated E2E profile with `--nomigrations` for the
functional pipeline, not against any existing application database. To exercise
the actual broker, use a temporary RabbitMQ vhost and remove only that vhost
afterwards. Never let the normal development worker consume test record IDs.
