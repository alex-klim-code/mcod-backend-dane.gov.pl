import os

import pytest
from django.core.files.base import ContentFile
from django.test import override_settings

from mcod.core.storages import ResourcesStorage


class Bucket:
    def __init__(self):
        self.objects = {}

    def exists(self, name):
        return name in self.objects

    def upload_from_bytes(self, name, content):
        self.objects[name] = content

    def download_as_bytes(self, name):
        return self.objects[name]

    def delete(self, name):
        del self.objects[name]


def test_resource_storage_restores_missing_local_copy_from_private_bucket(tmp_path, monkeypatch):
    storage = ResourcesStorage(location=str(tmp_path))
    bucket = Bucket()
    monkeypatch.setattr(storage, "_app_storage_client", lambda: bucket)
    with override_settings(REPLIT_APP_STORAGE_ENABLED=True):
        name = storage.save("sample.csv", ContentFile(b"device_id,name\nAED1,Example\n"))
        os.remove(str(tmp_path / name))
        with storage.open(name, "rb") as source:
            assert source.read() == b"device_id,name\nAED1,Example\n"
        assert name in bucket.objects


def test_resource_storage_does_not_accept_local_only_upload_on_bucket_failure(tmp_path, monkeypatch):
    storage = ResourcesStorage(location=str(tmp_path))
    bucket = Bucket()

    def reject_upload(name, content):
        raise RuntimeError("bucket unavailable")

    bucket.upload_from_bytes = reject_upload
    monkeypatch.setattr(storage, "_app_storage_client", lambda: bucket)
    with override_settings(REPLIT_APP_STORAGE_ENABLED=True):
        with pytest.raises(RuntimeError, match="bucket unavailable"):
            storage.save("sample.csv", ContentFile(b"test"))
    assert not (tmp_path / "sample.csv").exists()
