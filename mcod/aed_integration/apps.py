import logging

from django.apps import AppConfig
from django.db.models.signals import post_save
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("mcod")


class AEDIntegrationConfig(AppConfig):
    name = "mcod.aed_integration"
    verbose_name = _("AED Puls integration")

    def ready(self):
        from mcod.aed_integration.signals import schedule_aggregate_after_resource_save
        from mcod.resources.models import Resource

        post_save.connect(
            schedule_aggregate_after_resource_save,
            sender=Resource,
            dispatch_uid="aed_integration.schedule_aggregate_after_resource_save",
        )
