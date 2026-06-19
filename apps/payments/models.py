from django.db import models
from django.utils.crypto import get_random_string

class Payment(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("successful", "Successful"),
        ("failed", "Failed"),
    )

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payment",
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    currency = models.CharField(
        max_length=10,
        default="NGN",
    )

    reference = models.CharField(
        max_length=255,
        unique=True,
    )

    provider = models.CharField(
        max_length=50,
        default="paystack",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    gateway_transaction_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    failure_reason = models.TextField(
        blank=True,
        null=True,
    )

    raw_response = models.JSONField(
        blank=True,
        null=True,
    )

    # Idempotency key for ensuring payment is not processed twice
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        blank=True,
        null=True,
        help_text="Unique key to prevent duplicate payments"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.idempotency_key:
            self.idempotency_key = get_random_string(64)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.reference

class Invoice(models.Model):
    """Invoice model for tracking issued invoices to orders."""
    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("issued", "Issued"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
        ("cancelled", "Cancelled"),
    )

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="invoice"
    )

    invoice_number = models.CharField(
        max_length=50,
        unique=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft"
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    currency = models.CharField(
        max_length=10,
        default="NGN"
    )

    issued_at = models.DateTimeField(blank=True, null=True)
    due_date = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    notes = models.TextField(blank=True)

    pdf_file = models.FileField(
        upload_to="invoices/",
        blank=True,
        null=True,
        help_text="Generated PDF invoice"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invoice {self.invoice_number} - Order #{self.order.id}"

class TransactionRecord(models.Model):
    """Transaction record for audit trail and financial reconciliation."""
    TRANSACTION_TYPE_CHOICES = (
        ("payment", "Payment"),
        ("refund", "Refund"),
        ("settlement", "Settlement"),
        ("adjustment", "Adjustment"),
    )

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="transaction_records"
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPE_CHOICES
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    description = models.TextField(blank=True)

    reference_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="External gateway reference ID"
    )

    raw_data = models.JSONField(
        blank=True,
        null=True,
        help_text="Raw response from payment gateway"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.amount} ({self.reference_id})"

class PaymentWebhook(models.Model):
    """Track incoming webhooks from payment providers for audit."""
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("processed", "Processed"),
        ("failed", "Failed"),
    )

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="webhooks",
        blank=True,
        null=True
    )

    event_type = models.CharField(max_length=100)
    event_id = models.CharField(max_length=255, unique=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    payload = models.JSONField()

    error_message = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Webhook {self.event_type} - {self.event_id}"
