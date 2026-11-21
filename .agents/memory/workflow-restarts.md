---
name: Imported project workflow restarts
description: Avoid duplicate processes when restarting newly grouped Replit workflows.
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
