import pytest

from mcod.resources.models import ResourceFile


@pytest.fixture(autouse=True)
def isolated_resource_storage(tmp_path, monkeypatch):
    storage = ResourceFile._meta.get_field("file").storage
    monkeypatch.setattr(storage, "_location", str(tmp_path))
    monkeypatch.setattr(storage, "location", str(tmp_path))
    yield
