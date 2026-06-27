from django.db import models
from django.utils.crypto import get_random_string


class Warehouse(models.Model):
    """Warehouse model for storing inventory at specific locations."""

    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.CASCADE, related_name="warehouses"
    )

    branch = models.ForeignKey(
        "vendors.Branch", on_delete=models.CASCADE, related_name="warehouses"
    )

    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    capacity = models.PositiveIntegerField(
        default=1000, help_text="Maximum items warehouse can hold"
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["vendor", "branch", "name"]

    def __str__(self):
        return f"{self.vendor.name} - {self.branch.name} - {self.name}"


class Category(models.Model):
    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.CASCADE, related_name="categories"
    )

    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["vendor", "name"]

    def __str__(self):
        return f"{self.vendor.name} - {self.name}"


class Product(models.Model):
    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.CASCADE, related_name="products"
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )

    name = models.CharField(max_length=255)

    sku = models.CharField(max_length=50, unique=True, blank=True)

    description = models.TextField(blank=True)

    price = models.DecimalField(max_digits=12, decimal_places=2)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = self.generate_sku()
        super().save(*args, **kwargs)

    def generate_sku(self):
        return f"PRD-{get_random_string(8).upper()}"

    def __str__(self):
        return f"{self.name} ({self.sku})"


class Inventory(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="inventory_records"
    )

    branch = models.ForeignKey(
        "vendors.Branch", on_delete=models.CASCADE, related_name="inventory_records"
    )

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="inventory_records",
        null=True,
        blank=True,
        help_text="Specific warehouse within the branch (optional)",
    )

    quantity = models.PositiveIntegerField(default=0)

    low_stock_threshold = models.PositiveIntegerField(default=5)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["product", "branch", "warehouse"]

    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    def apply_change(self, change_quantity, adjustment_type):

        if adjustment_type == "stock_in":
            self.quantity += change_quantity

        elif adjustment_type == "stock_out":
            self.quantity -= change_quantity

        elif adjustment_type == "adjustment":
            self.quantity = change_quantity

        self.save()
        return self


class InventoryLog(models.Model):
    ADJUSTMENT_TYPES = (
        ("stock_in", "Stock In"),
        ("stock_out", "Stock Out"),
        ("adjustment", "Adjustment"),
    )

    inventory = models.ForeignKey(
        Inventory, on_delete=models.CASCADE, related_name="logs"
    )

    change_quantity = models.IntegerField()

    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPES)

    reason = models.TextField(blank=True)

    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="inventory_logs",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def apply_inventory_change(self):
        """
        Applies inventory change and queues
        low-stock notifications asynchronously.
        """

        from apps.notifications.tasks import send_notification_task

        inventory = self.inventory.apply_change(
            self.change_quantity, self.adjustment_type
        )

        if inventory.is_low_stock():
            send_notification_task.delay(
                vendor_id=inventory.product.vendor.id,
                notification_type="inventory",
                title="Low Stock Alert",
                message=(
                    f"{inventory.product.name} "
                    f"is low on stock ({inventory.quantity} left)"
                ),
            )

        return {"inventory": inventory, "is_low_stock": inventory.is_low_stock()}

    def __str__(self):
        return (
            f"{self.inventory.product.name} | "
            f"{self.adjustment_type} | "
            f"{self.change_quantity}"
        )
