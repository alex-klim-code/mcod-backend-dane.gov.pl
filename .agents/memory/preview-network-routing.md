---
name: Preview network routing
description: Why a public Replit preview hostname can fail a strict public-IP SSRF check inside the workspace.
---

The configured public preview hostname may resolve to a private Replit proxy
address from inside the workspace. It is not necessarily a broken public URL.

**Why:** A strict public-IP check rejected an authorized check of this project's
own API after the actual public-source download and import had succeeded.

**How to apply:** Keep public-source downloads restricted to public destinations,
including redirects. If testing the project's configured preview API requires
private proxy routing, use a separate verification client restricted to that
exact first-party origin. Never extend that exception to source-file clients
or arbitrary hosts.
