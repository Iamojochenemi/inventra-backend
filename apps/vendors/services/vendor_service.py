from django.db.models import Q

from apps.vendors.models import Vendor


def get_user_vendors(user):
    """Return all vendors the user owns or is staff on."""
    return Vendor.objects.filter(Q(owner=user) | Q(staff__user=user)).distinct()
