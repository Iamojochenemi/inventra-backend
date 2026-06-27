from django.conf import settings
from django.db import models


class Vendor(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendors"
    )

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Branch(models.Model):
    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.CASCADE, related_name="branches"
    )

    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["vendor", "name"]

    def __str__(self):
        return f"{self.vendor.name} - {self.name}"


class VendorStaff(models.Model):
    ROLE_CHOICES = (
        ("owner", "Owner"),
        ("manager", "Manager"),
        ("inventory", "Inventory Staff"),
        ("dispatcher", "Dispatcher"),
        ("rider", "Rider"),
    )

    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.CASCADE, related_name="staff"
    )

    branch = models.ForeignKey(
        "vendors.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_members",
    )

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("vendor", "user")

    def save(self, *args, **kwargs):
        # 🔥 GUARANTEE: always assign Main Branch
        if not self.branch:
            main_branch = self.vendor.branches.filter(name="Main Branch").first()

            if not main_branch:
                main_branch = Branch.objects.create(
                    vendor=self.vendor, name="Main Branch"
                )

            self.branch = main_branch

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} - {self.vendor.name} ({self.role})"


class VendorSettings(models.Model):
    """Vendor-specific configuration and preferences."""

    vendor = models.OneToOneField(
        Vendor, on_delete=models.CASCADE, related_name="settings"
    )

    # Business settings
    business_registration_number = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=10, default="NGN")

    # Notification preferences
    enable_email_notifications = models.BooleanField(default=True)
    enable_inventory_alerts = models.BooleanField(default=True)
    enable_order_notifications = models.BooleanField(default=True)
    enable_delivery_updates = models.BooleanField(default=True)

    # Payment settings
    auto_process_payments = models.BooleanField(default=False)
    payment_settlement_days = models.PositiveIntegerField(default=7)

    # Operational settings
    allow_orders_when_low_stock = models.BooleanField(default=False)
    auto_assign_deliveries = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Settings for {self.vendor.name}"


class VendorInvitation(models.Model):
    """Invite staff members to join a vendor."""

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("expired", "Expired"),
    )

    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="invitations"
    )

    email = models.EmailField()

    role = models.CharField(max_length=20, choices=VendorStaff.ROLE_CHOICES)

    invitation_token = models.CharField(max_length=255, unique=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_invitations",
    )

    accepted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_invitations",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ["vendor", "email"]
        ordering = ["-created_at"]

    def is_expired(self):
        """Check if invitation has expired."""
        from django.utils import timezone

        return timezone.now() > self.expires_at

    def __str__(self):
        return f"Invitation for {self.email} to {self.vendor.name} ({self.status})"
