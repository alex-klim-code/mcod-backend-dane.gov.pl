---
name: Preview browser asset cache
description: Stale screenshot CSS responses after changing the front proxy.
---

A preview screenshot can retain cached stylesheet responses, including an
incorrect MIME type from an earlier proxy configuration. It may show an
unstyled page even after the live server returns correct CSS.

**Why:** During the MCOD proxy setup, repeated preview captures retained an
unstyled login while a fresh Chromium context displayed the correct styles.

**How to apply:** Check current HTTP response headers and a genuinely fresh
browser context before changing the application's styles to compensate.
