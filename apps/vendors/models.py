from django.db import models
from django.conf import settings


class Vendor(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vendors"
    )

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Branch(models.Model):
    vendor = models.ForeignKey(
        "vendors.Vendor",
        on_delete=models.CASCADE,
        related_name="branches"
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
        "vendors.Vendor",
        on_delete=models.CASCADE,
        related_name="staff"
    )

    branch = models.ForeignKey(
        "vendors.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_members"
    )

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE
    )

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
                    vendor=self.vendor,
                    name="Main Branch"
                )

            self.branch = main_branch

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} - {self.vendor.name} ({self.role})"