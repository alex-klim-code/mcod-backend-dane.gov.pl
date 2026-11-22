"""Importer-local SDK connection reuse, pacing and retries, not an app change."""
import time


class RetryingStorage:
    def __init__(self, client, interval=1.0):
        self.client = client
        self.interval = interval
        self.last_call = 0

    def __getattr__(self, name):
        operation = getattr(self.client, name)
        if name not in ("exists", "upload_from_bytes", "download_as_bytes"):
            return operation

        def invoke(*args, **kwargs):
            from replit.object_storage.errors import TooManyRequestsError
            for attempt in range(7):
                time.sleep(max(0, self.last_call + self.interval - time.monotonic()))
                self.last_call = time.monotonic()
                try:
                    return operation(*args, **kwargs)
                except TooManyRequestsError:
                    if attempt == 6:
                        raise
                    time.sleep(min(32, 2 ** attempt))
        return invoke


def configure_import_storage():
    from mcod.resources.models import ResourceFile
    storage = ResourceFile._meta.get_field("file").storage
    if not getattr(storage, "_aed_import_retry_client", None):
        client = RetryingStorage(storage._app_storage_client())
        storage._aed_import_retry_client = client
        # Only this standalone process uses the adapter. The server's storage,
        # authentication, files, settings and original source stay unchanged.
        storage._app_storage_client = lambda: client
