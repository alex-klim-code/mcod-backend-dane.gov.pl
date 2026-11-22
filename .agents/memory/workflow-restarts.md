---
name: Imported project workflow restarts
description: Check process ownership and public port mappings after workflow restarts.
---

When individual workflows were initially auto-started and later grouped under a
parallel parent, restarting the parent left the original child processes alive
in this environment. The new copies then failed with occupied ports.

**Why:** This happened during initial setup despite a successful parent restart
response; that response alone did not establish that old child processes stopped.

**How to apply:** Prefer restarting the exact individual service workflow after
changes. If an initial parent restart reports occupied ports, inspect process
ownership and stop only the identified leftover processes before restarting.
Do not change application ports to work around duplicate processes.

Workflow operations can also restore older `[[ports]]` entries after a validated
configuration replacement. A successful config-write response does not establish
that the public routing stayed changed.

**Why:** Restarting the individual workflows restored Erlang port 4369 as external
port 80, while the healthy web app stayed on 5000. Internal HTTP returned 200 but
the standard public preview URL returned 502.

**How to apply:** After the necessary workflow restarts, recheck the actual
`.replit` port mappings and the proxied HTTP response. Correct the mappings using
the schema-validated configuration flow if they reverted. Verify that web port
5000 is the only public mapping and do not expose internal broker ports.
