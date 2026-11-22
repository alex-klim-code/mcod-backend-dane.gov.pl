---
name: Root login forms
description: Why displaying MCOD login at the root does not prove authentication submissions work.
---

When the proxy displays the login page at an anonymous root URL, the form must
still submit to the canonical login route. Compatibility redirects for old root
forms must preserve the POST body and remain on the browser's current origin.

**Why:** Production returned HTTP 200 for login submissions without validating
them: an empty form action submitted to the root, whose anonymous redirect was
intercepted and converted into a GET of the login page. A direct login-route POST
validated correctly. Checking only the rendered page missed this failure.

**How to apply:** Check rendered form actions and actual POST validation as well
as GET availability after proxy/login changes. A relative, method-preserving
redirect avoids downgrading HTTPS or exposing an internal proxy port. Do not
disable CSRF or lockout protection to repair a request sent to the wrong route.
