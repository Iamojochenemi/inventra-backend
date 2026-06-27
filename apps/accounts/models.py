from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.crypto import get_random_string


class User(AbstractUser):
    email = models.EmailField(unique=True)

    role = models.CharField(
        max_length=20,
        choices=[
            ("admin", "Admin"),
            ("manager", "Manager"),
            ("staff", "Staff"),
            ("vendor", "Vendor"),
        ],
        default="vendor",
    )

    phone_number = models.CharField(max_length=20, blank=True, null=True)

    # Email verification
    email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=255, blank=True, null=True)
    email_verification_sent_at = models.DateTimeField(blank=True, null=True)

    # Password reset
    password_reset_token = models.CharField(max_length=255, blank=True, null=True)
    password_reset_token_expires_at = models.DateTimeField(blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def generate_email_verification_token(self):
        """Generate a unique token for email verification."""
        self.email_verification_token = get_random_string(64)
        return self.email_verification_token

    def generate_password_reset_token(self):
        """Generate a unique token for password reset."""
        from datetime import timedelta

        from django.utils import timezone

        self.password_reset_token = get_random_string(64)
        self.password_reset_token_expires_at = timezone.now() + timedelta(hours=24)
        return self.password_reset_token

    def is_password_reset_token_valid(self):
        """Check if password reset token is still valid."""
        from django.utils import timezone

        if not self.password_reset_token_expires_at:
            return False
        return timezone.now() <= self.password_reset_token_expires_at

    def __str__(self):
        return self.email
