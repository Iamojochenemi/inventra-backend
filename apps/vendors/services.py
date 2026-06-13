from rest_framework.exceptions import PermissionDenied
from .models import VendorStaff


def get_vendor_staff(vendor, user):
    try:
        return VendorStaff.objects.get(
            vendor=vendor,
            user=user
        )

    except VendorStaff.DoesNotExist:
        raise PermissionDenied(
            "You do not belong to this vendor."
        )


def require_roles(staff, allowed_roles):
    if staff.role not in allowed_roles:
        # owner bypass always allowed
        if staff.role == "owner":
            return

        raise PermissionDenied(
            "You do not have permission to perform this action."
        )


def require_branch_access(staff, branch):
    """
    Enforces branch-level isolation.
    Owners bypass everything.
    """
    if staff.role == "owner":
        return

    if branch and staff.branch and staff.branch != branch:
        raise PermissionDenied(
            "You do not have access to this branch."
        )


def validate_vendor_access(vendor, user, allowed_roles=None, branch=None):
    staff = get_vendor_staff(vendor, user)

    # role check
    if allowed_roles:
        require_roles(staff, allowed_roles)

    # branch check (NEW)
    if branch:
        require_branch_access(staff, branch)

    return staff