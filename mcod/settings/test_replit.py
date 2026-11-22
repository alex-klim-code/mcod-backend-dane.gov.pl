"""Isolated integration tests on Replit; never point tests at the live schema."""

from mcod.settings.replit import *  # noqa: F403,F405

ENVIRONMENT = "test"
HEALTH_CHECK = False
ENABLE_CSRF = False
FALCON_CACHING_ENABLED = False
FALCON_LIMITER_ENABLED = False
# Never let model signals enqueue test record IDs into the development broker.
CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = False
REPLIT_APP_STORAGE_ENABLED = False
API_URL = "https://mcod-test.invalid/api"
FALCON_MIDDLEWARES = [  # noqa: F405
    item
    for item in FALCON_MIDDLEWARES  # noqa: F405
    if item != "mcod.core.api.middlewares.DjangoDBConnectionMiddleware"
]
ELASTICSEARCH_DSL_AUTOSYNC = False
CACHES = {
    name: {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "aed-test-{}".format(name),
    }
    for name in CACHES  # noqa: F405
}
CACHES["limiter"] = {
    "BACKEND": "django_redis.cache.RedisCache",
    "LOCATION": "redis://127.0.0.1:6379/13",
    "KEY_PREFIX": "aed-integration-test",
    "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
}
