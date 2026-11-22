import logging

from celery import shared_task

from mcod.aed_integration.models import AEDAggregateState
from mcod.aed_integration.services import rebuild_aggregate_catalog
from mcod.aed_integration.validation import AEDDataError
from mcod.resources.dga_utils import FailedValidationException, PendingValidationException

logger = logging.getLogger("mcod")


@shared_task(
    bind=True,
    max_retries=10,
    default_retry_delay=20,
    name="mcod.aed_integration.tasks.aggregate_aed_catalog_task",
)
def aggregate_aed_catalog_task(self):
    state, _created = AEDAggregateState.objects.get_or_create(singleton=True)
    try:
        return rebuild_aggregate_catalog().pk
    except PendingValidationException:
        if self.request.retries >= self.max_retries:
            state.mark_failed("validation_pending")
            logger.error("AED aggregate validation remained pending after retries.")
            return None
        raise self.retry(countdown=self.default_retry_delay)
    except (FailedValidationException, AEDDataError) as exc:
        code = getattr(exc, "code", "validation_failed")
        state.mark_failed(code)
        logger.error("AED aggregate build failed with code=%s.", code)
        return None
    except Exception as exc:
        state.mark_failed(type(exc).__name__)
        logger.error("AED aggregate build failed with error_type=%s.", type(exc).__name__)
        return None
