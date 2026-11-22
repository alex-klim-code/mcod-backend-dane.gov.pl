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
