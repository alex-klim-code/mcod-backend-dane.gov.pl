import logging

from django.db import transaction

logger = logging.getLogger("mcod")


def schedule_aggregate_after_resource_save(sender, instance, created, **kwargs):
    if instance.status != "published":
        return

    from mcod.aed_integration.models import AEDDatasetMapping
    from mcod.aed_integration.tasks import aggregate_aed_catalog_task

    if not AEDDatasetMapping.objects.filter(
        dataset_id=instance.dataset_id,
        organization_mapping__enabled=True,
    ).exists():
        return

    def enqueue():
        try:
            aggregate_aed_catalog_task.delay()
        except Exception as exc:
            logger.error(
                "Unable to queue AED catalog aggregation for resource %s (%s).",
                instance.pk,
                type(exc).__name__,
            )

    transaction.on_commit(enqueue)
