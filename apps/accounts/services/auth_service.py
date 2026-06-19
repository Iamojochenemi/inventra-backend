from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from datetime import timedelta
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

def send_verification_email(user, request=None):
    """
    Send email verification link to user.
    
    Args:
        user: User instance
        request: HTTP request for building absolute URLs
    """
    try:
        # Generate token
        token = user.generate_email_verification_token()
        user.email_verification_sent_at = timezone.now()
        user.save()

        # Build verification URL
        verification_url = f"{settings.FRONTEND_URL}/verify-email/?token={token}"
        
        # Prepare email context
        context = {
            'user': user,
            'verification_url': verification_url,
            'token': token,
        }

        # Render email template
        html_message = render_to_string(
            'emails/verify_email.html',
            context
        )
        plain_message = strip_tags(html_message)

        # Send email
        send_mail(
            subject='Verify your Inventra email',
            message=plain_message,
            from_email=None,  # Uses DEFAULT_FROM_EMAIL
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Verification email sent to {user.email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {str(e)}")
        return False

def verify_email(token):
    """
    Verify email token and mark user as verified.
    
    Args:
        token: Verification token
        
    Returns:
        Tuple: (success: bool, user: User or None, message: str)
    """
    try:
        user = User.objects.get(email_verification_token=token)
        
        if user.email_verified:
            return True, user, "Email already verified"
        
        # Mark as verified
        user.email_verified = True
        user.email_verification_token = None
        user.save()
        
        logger.info(f"Email verified for user {user.email}")
        return True, user, "Email verified successfully"
        
    except User.DoesNotExist:
        logger.warning(f"Invalid verification token: {token}")
        return False, None, "Invalid verification token"

def send_password_reset_email(user, request=None):
    """
    Send password reset link to user.
    
    Args:
        user: User instance
        request: HTTP request for building absolute URLs
    """
    try:
        # Generate token (24 hour expiry)
        token = user.generate_password_reset_token()
        user.save()

        # Build reset URL
        reset_url = f"{settings.FRONTEND_URL}/reset-password/?token={token}"
        
        # Prepare email context
        context = {
            'user': user,
            'reset_url': reset_url,
            'token': token,
            'expiry_hours': 24,
        }

        # Render email template
        html_message = render_to_string(
            'emails/password_reset.html',
            context
        )
        plain_message = strip_tags(html_message)

        # Send email
        send_mail(
            subject='Reset your Inventra password',
            message=plain_message,
            from_email=None,  # Uses DEFAULT_FROM_EMAIL
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Password reset email sent to {user.email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send password reset email to {user.email}: {str(e)}")
        return False

def reset_password(token, new_password):
    """
    Reset user password with token.
    
    Args:
        token: Password reset token
        new_password: New password
        
    Returns:
        Tuple: (success: bool, user: User or None, message: str)
    """
    try:
        user = User.objects.get(password_reset_token=token)
        
        # Check token validity
        if not user.is_password_reset_token_valid():
            return False, None, "Password reset token expired"
        
        # Update password
        user.set_password(new_password)
        user.password_reset_token = None
        user.password_reset_token_expires_at = None
        user.save()
        
        logger.info(f"Password reset for user {user.email}")
        return True, user, "Password reset successfully"
        
    except User.DoesNotExist:
        logger.warning(f"Invalid password reset token: {token}")
        return False, None, "Invalid password reset token"

def get_or_create_user_from_email(email, role="vendor"):
    """
    Get or create user from email (useful for invitations).
    
    Args:
        email: User email
        role: User role
        
    Returns:
        Tuple: (user: User, created: bool)
    """
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            'username': email.split('@')[0],
            'role': role,
        }
    )
    return user, created