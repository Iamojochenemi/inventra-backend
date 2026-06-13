from django.db import transaction

from .models import Delivery
from apps.notifications.tasks import send_notification_task


def create_delivery_from_order(order):
    """
    Create a delivery for a confirmed order.

    - Idempotent (prevents duplicates)
    - Safe transaction
    - Triggers async notification when created
    """

    if not order:
        return None

    with transaction.atomic():

        delivery, created = Delivery.objects.get_or_create(
            order=order,
            defaults={
                "status": "pending"
            }
        )

        # Notify only when a new delivery is created
        if created:
            send_notification_task.delay(
                vendor_id=order.vendor.id,
                notification_type="delivery",
                title="New Delivery Created",
                message=f"Delivery created for Order #{order.id}"
            )

        return delivery