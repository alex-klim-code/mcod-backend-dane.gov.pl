from django.contrib import admin
from django.core.exceptions import ValidationError

from mcod.aed_integration.models import (
    AEDAggregateState,
    AEDDatasetMapping,
    AEDIntegrationAudit,
    AEDOrganizationMapping,
    AEDOrganizationRequest,
)


@admin.register(AEDOrganizationMapping)
class AEDOrganizationMappingAdmin(admin.ModelAdmin):
    list_display = ("external_organization_id", "organization", "enabled")
    list_filter = ("enabled",)
    search_fields = ("external_organization_id", "organization__title", "organization__slug")
    filter_horizontal = ("default_tags",)
    fields = (
        "external_organization_id",
        "organization",
        "default_category",
        "default_tags",
        "enabled",
        "can_manage_institution",
        "can_adopt_datasets",
    )


@admin.register(AEDDatasetMapping)
class AEDDatasetMappingAdmin(admin.ModelAdmin):
    list_display = ("external_dataset_id", "organization_mapping", "dataset")
    search_fields = (
        "external_dataset_id",
        "organization_mapping__external_organization_id",
        "dataset__title",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(AEDOrganizationRequest)
class AEDOrganizationRequestAdmin(admin.ModelAdmin):
    list_display = ("external_organization_id", "organization_name", "request_type", "organization", "status")
    list_filter = ("status", "request_type")
    search_fields = ("external_organization_id", "organization_name")
    readonly_fields = ("status", "reviewed_by", "reviewed_at", "created_at", "updated_at")
    filter_horizontal = ("default_tags",)
    actions = ("approve_requests", "reject_requests")

    def _review(self, request, queryset, approve):
        from mcod.aed_integration.institutions import review_request
        for item in queryset:
            try:
                review_request(item.pk, approve, request.user)
            except ValidationError as exc:
                self.message_user(request, str(exc), level="error")
            else:
                self.message_user(request, "{}: {}".format(item.external_organization_id, "approved" if approve else "rejected"))

    def approve_requests(self, request, queryset):
        self._review(request, queryset, True)

    approve_requests.short_description = "Approve selected organization requests"
    approve_requests.allowed_permissions = ("change",)

    def reject_requests(self, request, queryset):
        self._review(request, queryset, False)

    reject_requests.short_description = "Reject selected organization requests"
    reject_requests.allowed_permissions = ("change",)


@admin.register(AEDAggregateState)
class AEDAggregateStateAdmin(admin.ModelAdmin):
    list_display = ("status", "owner_mapping", "dataset", "published_resource", "record_count", "last_run_at")
    readonly_fields = (
        "singleton",
        "dataset",
        "pending_resource",
        "published_resource",
        "status",
        "source_fingerprint",
        "record_count",
        "last_error",
        "last_run_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return not AEDAggregateState.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AEDIntegrationAudit)
class AEDIntegrationAuditAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "action",
        "outcome",
        "code",
        "external_organization_id",
        "external_dataset_id",
        "dataset",
        "resource",
    )
    list_filter = ("action", "outcome", "created_at")
    search_fields = ("external_organization_id", "external_dataset_id", "code")
    readonly_fields = tuple(field.name for field in AEDIntegrationAudit._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
