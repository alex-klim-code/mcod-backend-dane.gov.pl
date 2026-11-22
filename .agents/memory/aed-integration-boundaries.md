---
name: AED Puls integration boundaries
description: Product constraints for MCOD integration ownership, roles, and retained source history.
---

MCOD is the data publication backend for AED Puls, which lives in a separate
Replit project. AED Puls alone owns ADMIN, USER and ORGANIZATIONS roles.
Do not synchronize its users or logins into MCOD or use a superadministrator
as the integration identity.

**Why:** The user explicitly required backend-to-backend communication with
limited authority, rather than merging the two applications' authentication.

**How to apply:** Keep authorization for AED Puls users in AED Puls; use
administrator-approved mappings to MCOD institutions for publication. Do not
assume access to the AED Puls source code from this repository.

Preserve existing MCOD users, datasets and resources. Do not reuse the DGA
national-list replacement behavior to delete prior AED aggregate resources.

**Why:** The user prohibited destructive resets and removal of existing data;
the hackathon needs traceable source provenance and aggregation history.

**How to apply:** Treat a new aggregate as a separately validated MCOD
publication and retain prior versions. Report incomplete worker/storage/
publication verification plainly rather than treating a draft as published.
