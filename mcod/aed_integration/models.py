from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils import timezone


class AEDOrganizationMapping(models.Model):
    external_organization_id = models.CharField(max_length=128, unique=True)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="aed_integration_mappings",
    )
    default_category = models.ForeignKey(
        "categories.Category",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="aed_integration_mappings",
    )
    default_tags = models.ManyToManyField(
        "tags.Tag",
        blank=True,
        related_name="aed_integration_mappings",
    )
    enabled = models.BooleanField(default=True)
    can_manage_institution = models.BooleanField(default=False)
    can_adopt_datasets = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("external_organization_id",)
        verbose_name = "AED organization mapping"
        verbose_name_plural = "AED organization mappings"

    def __str__(self):
        return "{} → {}".format(self.external_organization_id, self.organization)

    def clean(self):
        if self.pk and self.datasets.exclude(
            dataset__organization_id=self.organization_id
        ).exists():
            raise ValidationError(
                "This mapping has datasets owned by another institution. "
                "Create a new mapping instead of changing its owner."
            )


class AEDDatasetMapping(models.Model):
    organization_mapping = models.ForeignKey(
        AEDOrganizationMapping,
        on_delete=models.PROTECT,
        related_name="datasets",
    )
    external_dataset_id = models.CharField(max_length=128)
    dataset = models.OneToOneField(
        "datasets.Dataset",
        on_delete=models.PROTECT,
        related_name="aed_integration_mapping",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("organization_mapping", "external_dataset_id"),)
        ordering = ("external_dataset_id",)
        verbose_name = "AED dataset mapping"
        verbose_name_plural = "AED dataset mappings"

    def clean(self):
        if self.dataset_id and self.organization_mapping_id:
            if self.dataset.organization_id != self.organization_mapping.organization_id:
                raise ValidationError("The MCOD dataset must belong to the mapped institution.")

    def __str__(self):
        return "{} → {}".format(self.external_dataset_id, self.dataset_id)


class AEDOrganizationRequest(models.Model):
    """Approval belongs to MCOD staff, never to the shared bearer itself."""

    external_organization_id = models.CharField(max_length=128, unique=True)
    organization_name = models.CharField(max_length=200)
    request_type = models.CharField(max_length=8, choices=(("link", "Link"), ("create", "Create")))
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, null=True, blank=True,
        related_name="aed_link_requests",
    )
    status = models.CharField(
        max_length=10, default="pending",
        choices=(("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")),
    )
    can_manage_institution = models.BooleanField(default=False)
    can_adopt_datasets = models.BooleanField(default=False)
    default_category = models.ForeignKey(
        "categories.Category", on_delete=models.PROTECT, null=True, blank=True,
        related_name="aed_link_requests",
    )
    default_tags = models.ManyToManyField("tags.Tag", blank=True, related_name="aed_link_requests")
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="aed_reviews", editable=False,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.request_type == "link" and not self.organization_id:
            raise ValidationError({"organization": "An existing institution is required for a link request."})
        if self.request_type == "create" and self.organization_id:
            raise ValidationError({"organization": "A creation request cannot select an existing institution."})

    def __str__(self):
        return "{} ({})".format(self.external_organization_id, self.status)


class AEDAggregateState(models.Model):
    STATUS_IDLE = "idle"
    STATUS_QUEUED = "queued"
    STATUS_BUILDING = "building"
    STATUS_PUBLISHED = "published"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_IDLE, "Idle"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_BUILDING, "Building"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_FAILED, "Failed"),
    )

    # This row is intentionally a singleton: the national catalog is one real
    # MCOD dataset/resource, not a second copy of the catalog in a private table.
    singleton = models.BooleanField(default=True, unique=True, editable=False)
    owner_mapping = models.ForeignKey(
        AEDOrganizationMapping,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="aggregate_states",
    )
    license_chosen = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=(
            (1, "CC0 1.0"),
            (2, "CC BY 4.0"),
            (3, "CC BY-SA 4.0"),
            (4, "CC BY-NC 4.0"),
            (5, "CC BY-NC-SA 4.0"),
            (6, "CC BY-ND 4.0"),
            (7, "CC BY-NC-ND 4.0"),
        ),
    )
    update_frequency = models.CharField(max_length=50, blank=True)
    has_dynamic_data = models.NullBooleanField()
    has_high_value_data = models.NullBooleanField()
    has_high_value_data_from_ec_list = models.NullBooleanField()
    has_research_data = models.NullBooleanField()
    dataset = models.OneToOneField(
        "datasets.Dataset",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="aed_aggregate_state",
    )
    pending_resource = models.ForeignKey(
        "resources.Resource",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="aed_aggregate_pending_states",
    )
    published_resource = models.ForeignKey(
        "resources.Resource",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="aed_aggregate_published_states",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_IDLE)
    source_fingerprint = models.CharField(max_length=64, blank=True)
    record_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AED national catalog"
        verbose_name_plural = "AED national catalog"

    def mark_failed(self, message):
        self.status = self.STATUS_FAILED
        self.last_error = str(message)[:2000]
        self.last_run_at = timezone.now()
        self.save(update_fields=("status", "last_error", "last_run_at", "updated_at"))


class AEDIntegrationAudit(models.Model):
    action = models.CharField(max_length=64)
    outcome = models.CharField(max_length=24)
    code = models.CharField(max_length=64, blank=True)
    details = JSONField(default=dict, blank=True)
    external_organization_id = models.CharField(max_length=128, blank=True)
    external_dataset_id = models.CharField(max_length=128, blank=True)
    dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aed_integration_audit",
    )
    resource = models.ForeignKey(
        "resources.Resource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="aed_integration_audit",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "AED integration audit event"
        verbose_name_plural = "AED integration audit events"
