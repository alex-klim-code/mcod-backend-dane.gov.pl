"""Connection compatibility for the imported application's older libpq."""

import re


def neon_compatible_database(database, libpq_version):
    """Route legacy clients to the endpoint already named in the managed host.

    libpq before PostgreSQL 14 does not send TLS SNI. Neon supports an explicit
    endpoint startup option instead. Do not change credentials, TLS settings,
    non-Neon connections, or an explicitly configured endpoint.
    """
    configured = dict(database)
    options = dict(database.get("OPTIONS") or {})
    host = (database.get("HOST") or "").lower().rstrip(".")
    if libpq_version >= 140000 or not host.endswith(".neon.tech"):
        return configured
    endpoint = host.split(".", 1)[0]
    if endpoint.endswith("-pooler"):
        endpoint = endpoint[:-7]
    if not re.fullmatch(r"ep-[a-z0-9-]+", endpoint):
        return configured
    startup_options = options.get("options", "")
    if re.search(r"(?:^|\s)(?:-c\s+)?endpoint\s*=", startup_options):
        return configured
    options["options"] = "{} endpoint={}".format(startup_options, endpoint).strip()
    configured["OPTIONS"] = options
    return configured
