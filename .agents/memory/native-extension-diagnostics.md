---
name: Native extension diagnostics
description: Why isolated imports are insufficient when diagnosing legacy Django startup crashes.
---

Reproduce native crashes with full Django initialization before changing
dependencies. Passing isolated imports does not establish that native extensions
are safe in the application's nested import order.

**Why:** Individual imports of psycopg2 and zope.interface passed, while Django
initialization crashed in zope.interface's optional C accelerator through
Sentry/gevent. The full build succeeded with the supported Python implementation.
Treating that crash as another database routing failure would target the wrong
dependency.

**How to apply:** Use fault-handler tracebacks and the actual failing build
command. Preserve the tested compatibility policy documented in `replit.md`;
do not remove it based only on successful standalone imports or connection tests.
