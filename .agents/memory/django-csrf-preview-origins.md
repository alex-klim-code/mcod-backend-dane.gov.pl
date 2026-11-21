---
name: Django CSRF preview origins
description: CSRF trusted-origin matching with Django 2.2 and proxied preview ports.
---

Django 2.2 treats `CSRF_TRUSTED_ORIGINS` entries as host strings, not modern
scheme-based origins. Its domain-suffix matching also includes the port, so a
proxied HTTPS Referer on `host:5000` does not match a trusted entry for
`host` or `.replit.dev`. Trust the exact Replit development hostname and
external preview port, not the entire Replit domain suffix.

**Why:** The proxy preserves `:5000` in the browser Referer while the request
reaching Django may identify a different host/port; sign-in POSTs then fail the
referer check.

**How to apply:** For Django 2.2 on Replit, construct the trusted origin from
`REPLIT_DEV_DOMAIN` and the configured external port. Verify a CSRF-enforced
POST with a preview Referer while keeping invalid credentials rejected.
