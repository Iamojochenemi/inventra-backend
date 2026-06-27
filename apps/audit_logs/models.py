from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditLog(models.Model):
    """
    Track all changes to entities in the system for compliance and auditing.
    Supports generic logging of any model instance.
    """

    ACTION_CHOICES = (
        ("create", "Created"),
        ("update", "Updated"),
        ("delete", "Deleted"),
        ("restore", "Restored"),
    )

    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="audit_logs"
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)

    object_id = models.PositiveIntegerField()

    content_object = GenericForeignKey("content_type", "object_id")

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    old_values = models.JSONField(
        blank=True, null=True, help_text="Previous values of changed fields"
    )

    new_values = models.JSONField(
        blank=True, null=True, help_text="New values of changed fields"
    )

    ip_address = models.GenericIPAddressField(
        blank=True, null=True, help_text="IP address where change originated"
    )

    user_agent = models.TextField(
        blank=True, null=True, help_text="User agent string from request"
    )

    reason = models.TextField(
        blank=True, help_text="Reason for the change (if provided)"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.get_action_display()} "
            f"{self.content_type.name} "
            f"by {self.user} at {self.created_at}"
        )


class EntitySnapshot(models.Model):
    """
    Periodically save snapshots of important entities for historical reference.
    Useful for tracking state changes over time.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)

    object_id = models.PositiveIntegerField()

    content_object = GenericForeignKey("content_type", "object_id")

    snapshot_data = models.JSONField(
        help_text="Complete state of entity at snapshot time"
    )

    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Why snapshot was taken (e.g., 'Status change', 'Order completion')",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=[
                    "content_type",
                    "object_id",
                    "created_at",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"Snapshot of {self.content_type.name} "
            f"#{self.object_id} at {self.created_at}"
        )
