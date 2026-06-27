from django.db import models
from django.utils import timezone

from apps.notifications.tasks import send_notification_task


class Delivery(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("assigned", "Assigned"),
        ("picked_up", "Picked Up"),
        ("in_transit", "In Transit"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    )

    ALLOWED_TRANSITIONS = {
        "pending": ["assigned", "cancelled"],
        "assigned": ["picked_up", "cancelled"],
        "picked_up": ["in_transit", "failed"],
        "in_transit": ["delivered", "failed"],
        "delivered": [],
        "failed": [],
        "cancelled": [],
    }

    order = models.OneToOneField(
        "orders.Order", on_delete=models.CASCADE, related_name="delivery"
    )

    assigned_rider = models.ForeignKey(
        "vendors.VendorStaff",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    recipient_name = models.CharField(max_length=255, blank=True)

    delivered_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def change_status(self, new_status, changed_by=None):

        old_status = self.status

        allowed = self.ALLOWED_TRANSITIONS.get(old_status, [])

        if new_status not in allowed:
            raise ValueError(f"Invalid transition from {old_status} to {new_status}")

        self.status = new_status

        if new_status == "delivered":
            self.delivered_at = timezone.now()

        self.save()

        # Queue vendor notification asynchronously
        send_notification_task.delay(
            vendor_id=self.order.vendor.id,
            notification_type="delivery",
            title="Delivery Update",
            message=f"Order #{self.order.id} is now {new_status}",
        )

        return self

    def __str__(self):
        return f"Delivery #{self.id} - Order #{self.order.id}"


class DeliveryLog(models.Model):
    EVENT_TYPES = (
        ("status_change", "Status Change"),
        ("rider_assignment", "Rider Assignment"),
    )

    delivery = models.ForeignKey(
        Delivery, on_delete=models.CASCADE, related_name="logs"
    )

    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)

    previous_value = models.CharField(max_length=255, blank=True)

    new_value = models.CharField(max_length=255, blank=True)

    changed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="delivery_logs",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Delivery {self.delivery.id} - {self.event_type}"
