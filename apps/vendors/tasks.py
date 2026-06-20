import logging

from celery import shared_task

from apps.vendors.models import VendorInvitation
from apps.vendors.services.invitation_service import send_invitation_email

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
)
def send_vendor_invitation_email_task(self, invitation_id):
    """
    Fetch a VendorInvitation by ID and send the invitation email asynchronously.

    Retries up to 3 times with a 60s delay on any exception.
    """
    try:
        invitation = VendorInvitation.objects.get(id=invitation_id)
    except VendorInvitation.DoesNotExist:
        logger.error(
            "send_vendor_invitation_email_task: invitation %s not found",
            invitation_id,
        )
        return {"success": False, "error": "Invitation not found"}

    success = send_invitation_email(invitation)

    if success:
        logger.info("Invitation email sent to %s", invitation.email)
    else:
        logger.warning(
            "Failed to send invitation email to %s (invitation %s)",
            invitation.email,
            invitation_id,
        )

    return {
        "success": success,
        "invitation_id": invitation_id,
        "email": invitation.email,
    }
