from django.contrib import admin

from mcod.aed_integration.models import (
    AEDAggregateState,
    AEDDatasetMapping,
    AEDIntegrationAudit,
    AEDOrganizationMapping,
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

    def has_delete_permission(self, request, obj=None):
        return False
