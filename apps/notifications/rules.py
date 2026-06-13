from apps.vendors.models import VendorStaff


def get_notification_recipients(vendor, notification_type):
    """
    Returns users who should receive a given notification type.
    Owner and manager ALWAYS receive all notifications.
    """

    base_roles = ["owner", "manager"]

    roles_map = {
        "inventory": ["inventory"],
        "order": ["dispatcher"],
        "delivery": ["rider"],
        "system": [],
    }

    extra_roles = roles_map.get(notification_type, [])

    allowed_roles = list(set(base_roles + extra_roles))

    staff = VendorStaff.objects.filter(
        vendor=vendor,
        role__in=allowed_roles
    ).select_related("user")

    return [s.user for s in staff]