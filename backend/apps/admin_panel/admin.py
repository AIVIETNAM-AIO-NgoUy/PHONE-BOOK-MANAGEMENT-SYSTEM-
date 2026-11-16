"""Django admin site registration for AuditLog."""

from django.contrib import admin

from apps.admin_panel.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only Django admin view for audit log inspection."""

    list_display = (
        "id",
        "timestamp",
        "action",
        "actor_username_snapshot",
        "target_username_snapshot",
        "ip_address",
    )
    list_filter = ("action", "timestamp")
    search_fields = ("actor_username_snapshot", "target_username_snapshot", "ip_address")
    readonly_fields = (
        "actor",
        "actor_username_snapshot",
        "target_user",
        "target_username_snapshot",
        "action",
        "details",
        "ip_address",
        "user_agent",
        "timestamp",
    )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
