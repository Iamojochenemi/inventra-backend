from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.crypto import get_random_string
from django.conf import settings
from datetime import timedelta
import logging

from apps.vendors.models import VendorInvitation, VendorStaff, Branch
from apps.accounts.services.auth_service import get_or_create_user_from_email


logger = logging.getLogger(__name__)

def create_invitation(vendor, email, role, created_by, request=None):
    """
    Create a vendor staff invitation.
    
    Args:
        vendor: Vendor instance
        email: Email to invite
        role: Staff role
        created_by: User creating the invitation
        request: HTTP request (optional)
        
    Returns:
        VendorInvitation instance
    """
    try:
        # Check if user already exists in vendor
        existing_staff = VendorStaff.objects.filter(
            vendor=vendor,
            user__email=email
        ).exists()
        
        if existing_staff:
            raise ValueError(f"{email} is already a staff member")
        
        # Check for existing pending invitation
        existing_invitation = VendorInvitation.objects.filter(
            vendor=vendor,
            email=email,
            status="pending"
        ).first()
        
        if existing_invitation and not existing_invitation.is_expired():
            raise ValueError(f"Active invitation already exists for {email}")
        
        # Generate invitation token
        invitation_token = get_random_string(64)
        
        # Create invitation (expires in 7 days)
        invitation = VendorInvitation.objects.create(
            vendor=vendor,
            email=email,
            role=role,
            invitation_token=invitation_token,
            created_by=created_by,
            expires_at=timezone.now() + timedelta(days=7)
        )
        
        logger.info(f"Invitation created for {email} to {vendor.name}")
        return invitation
        
    except Exception as e:
        logger.error(f"Failed to create invitation: {str(e)}")
        raise

def send_invitation_email(invitation, request=None):
    """
    Send invitation email to user.
    
    Args:
        invitation: VendorInvitation instance
        request: HTTP request (optional)
        
    Returns:
        bool: Success status
    """
    try:
        # Build invitation URL
        invitation_url = f"{settings.FRONTEND_URL}/accept-invitation/?token={invitation.invitation_token}"
        
        # Prepare email context
        context = {
            'vendor': invitation.vendor,
            'email': invitation.email,
            'role': invitation.get_role_display(),
            'invitation_url': invitation_url,
            'token': invitation.invitation_token,
            'expires_at': invitation.expires_at,
        }
        
        # Render email template
        html_message = render_to_string(
            'emails/vendor_invitation.html',
            context
        )
        plain_message = strip_tags(html_message)
        
        # Send email
        send_mail(
            subject=f"Join {invitation.vendor.name} on Inventra",
            message=plain_message,
            from_email=None,  # Uses DEFAULT_FROM_EMAIL
            recipient_list=[invitation.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Invitation email sent to {invitation.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send invitation email to {invitation.email}: {str(e)}")
        return False

def accept_invitation(token, password=None):
    """
    Accept vendor invitation and create staff member.
    
    Args:
        token: Invitation token
        password: Password if creating new user (optional)
        
    Returns:
        Tuple: (success: bool, vendor_staff: VendorStaff or None, message: str)
    """
    try:
        invitation = VendorInvitation.objects.get(invitation_token=token)
        
        # Check if invitation is valid
        if invitation.status != "pending":
            return False, None, f"Invitation already {invitation.status}"
        
        if invitation.is_expired():
            invitation.status = "expired"
            invitation.save()
            return False, None, "Invitation has expired"
        
        # Get or create user
        user, created = get_or_create_user_from_email(invitation.email, role="vendor")
        
        if created and password:
            user.set_password(password)
            user.save()
        
        # Get or create Main Branch
        main_branch = invitation.vendor.branches.filter(name="Main Branch").first()
        if not main_branch:
            main_branch = Branch.objects.create(
                vendor=invitation.vendor,
                name="Main Branch"
            )
        
        # Create staff member
        vendor_staff, staff_created = VendorStaff.objects.get_or_create(
            vendor=invitation.vendor,
            user=user,
            defaults={
                'role': invitation.role,
                'branch': main_branch,
            }
        )
        
        # Mark invitation as accepted
        invitation.status = "accepted"
        invitation.accepted_by = user
        invitation.accepted_at = timezone.now()
        invitation.save()
        
        logger.info(f"Invitation accepted for {invitation.email} to {invitation.vendor.name}")
        return True, vendor_staff, "Invitation accepted successfully"
        
    except VendorInvitation.DoesNotExist:
        logger.warning(f"Invalid invitation token: {token}")
        return False, None, "Invalid invitation token"
    except Exception as e:
        logger.error(f"Failed to accept invitation: {str(e)}")
        return False, None, str(e)

def reject_invitation(token):
    """
    Reject vendor invitation.
    
    Args:
        token: Invitation token
        
    Returns:
        Tuple: (success: bool, message: str)
    """
    try:
        invitation = VendorInvitation.objects.get(invitation_token=token)
        
        if invitation.status != "pending":
            return False, f"Invitation already {invitation.status}"
        
        invitation.status = "rejected"
        invitation.save()
        
        logger.info(f"Invitation rejected for {invitation.email}")
        return True, "Invitation rejected"
        
    except VendorInvitation.DoesNotExist:
        logger.warning(f"Invalid invitation token: {token}")
        return False, "Invalid invitation token"

def resend_invitation(invitation_id):
    """
    Resend invitation email.
    
    Args:
        invitation_id: VendorInvitation ID
        
    Returns:
        bool: Success status
    """
    try:
        invitation = VendorInvitation.objects.get(id=invitation_id)
        
        if invitation.status != "pending":
            raise ValueError(f"Cannot resend {invitation.status} invitation")
        
        if invitation.is_expired():
            # Refresh expiration
            invitation.expires_at = timezone.now() + timedelta(days=7)
            invitation.save()
        
        return send_invitation_email(invitation)
        
    except Exception as e:
        logger.error(f"Failed to resend invitation: {str(e)}")
        return False