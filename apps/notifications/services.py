from django.core.exceptions import ObjectDoesNotExist

from apps.vendors.models import Vendor

from .models import Notification
from .rules import get_notification_recipients


def create_notification(user, type, title, message):
    """
    Single-user notification (kept for backward compatibility).
    """

    return Notification.objects.create(
        user=user, type=type, title=title, message=message
    )


def create_bulk_notifications(users, notification_type, title, message):
    """
    Core reusable notification engine.
    """

    notifications = [
        Notification(user=user, type=notification_type, title=title, message=message)
        for user in users
    ]

    return Notification.objects.bulk_create(notifications)


def create_vendor_notification(vendor_id, notification_type, title, message):
    """
    Business-level notification creator.

    All apps should call this function for vendor-wide notifications.
    """

    try:
        vendor = Vendor.objects.get(id=vendor_id)
    except ObjectDoesNotExist:
        return None  # silently fail instead of crashing async tasks

    users = get_notification_recipients(vendor, notification_type)

    if not users:
        return []

    return create_bulk_notifications(
        users=users, notification_type=notification_type, title=title, message=message
    )
