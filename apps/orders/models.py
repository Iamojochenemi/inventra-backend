from django.db import models


class Order(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    )

    # 🔥 ORDER FLOW RULES (STATE MACHINE)
    ALLOWED_TRANSITIONS = {
        "pending": ["confirmed", "cancelled"],
        "confirmed": ["completed", "cancelled"],
        "completed": [],
        "cancelled": [],
    }

    vendor = models.ForeignKey(
        "vendors.Vendor",
        on_delete=models.CASCADE,
        related_name="orders"
    )

    branch = models.ForeignKey(
        "vendors.Branch",
        on_delete=models.CASCADE,
        related_name="orders"
    )

    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=50, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_orders"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.vendor.name}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.CASCADE
    )

    quantity = models.PositiveIntegerField()

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
    
class OrderStatusLog(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_logs"
    )

    previous_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)

    changed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.order.id}: {self.previous_status} → {self.new_status}"