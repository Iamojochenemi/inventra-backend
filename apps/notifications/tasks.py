from celery import shared_task

from apps.notifications.services import create_vendor_notification


@shared_task
def send_notification_task(vendor_id, notification_type, title, message):
    notifications = create_vendor_notification(
        vendor_id=vendor_id,
        notification_type=notification_type,
        title=title,
        message=message,
    )

    if notifications is None:
        notifications = []

    return {"count": len(notifications), "type": notification_type, "title": title}
