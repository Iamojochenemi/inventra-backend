from django.contrib import admin
from django.utils.html import format_html

from .models import AuditLog, EntitySnapshot


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "action_badge",
        "content_type",
        "user",
        "ip_address",
        "created_at",
    )
    list_filter = ("action", "content_type", "created_at", "user")
    search_fields = ("user__email", "ip_address", "reason")
    readonly_fields = (
        "created_at",
        "content_type",
        "object_id",
        "old_values",
        "new_values",
        "user_agent",
    )
    date_hierarchy = "created_at"

    fieldsets = (
        ("Change Information", {"fields": ("user", "action", "reason")}),
        ("Target Entity", {"fields": ("content_type", "object_id")}),
        ("Values", {"fields": ("old_values", "new_values")}),
        ("Request Metadata", {"fields": ("ip_address", "user_agent")}),
        ("Timestamp", {"fields": ("created_at",)}),
    )

    def action_badge(self, obj):
        colors = {
            "create": "#28a745",
            "update": "#ffc107",
            "delete": "#dc3545",
            "restore": "#17a2b8",
        }
        color = colors.get(obj.action, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_action_display(),
        )

    action_badge.short_description = "Action"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EntitySnapshot)
class EntitySnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "content_type", "object_id", "reason", "created_at")
    list_filter = ("content_type", "reason", "created_at")
    search_fields = ("reason",)
    readonly_fields = ("content_type", "object_id", "snapshot_data", "created_at")
    date_hierarchy = "created_at"

    fieldsets = (
        ("Entity", {"fields": ("content_type", "object_id")}),
        ("Snapshot", {"fields": ("snapshot_data", "reason")}),
        ("Timestamp", {"fields": ("created_at",)}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
