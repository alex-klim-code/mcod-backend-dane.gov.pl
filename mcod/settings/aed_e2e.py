"""Opt-in isolated database/queue/indexes with real App Storage and validators."""

import uuid

from mcod.settings.test_replit import *  # noqa: F403,F405

_namespace = "aed-e2e-" + uuid.uuid4().hex
API_URL = "https://mcod-e2e.invalid/api"
REPLIT_APP_STORAGE_ENABLED = True
CONSTANCE_DATABASE_CACHE_BACKEND = None
CACHES["default"] = {  # noqa: F405
    "BACKEND": "django_redis.cache.RedisCache",
    "LOCATION": "redis://127.0.0.1:6379/13",
    "KEY_PREFIX": _namespace,
    "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
}
ELASTICSEARCH_INDEX_NAMES = {
    name: "{}-{}".format(_namespace, name)
    for name in ELASTICSEARCH_INDEX_NAMES  # noqa: F405
}
ELASTICSEARCH_COMMON_ALIAS_NAME = _namespace + "-common"
ELASTICSEARCH_DSL_SEARCH_INDEX_ALIAS = {ELASTICSEARCH_COMMON_ALIAS_NAME: {}}
ELASTICSEARCH_INDEX_PREFIX = _namespace + "-"
