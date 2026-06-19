from django.contrib import admin

from .models import Payment, Invoice, TransactionRecord, PaymentWebhook


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "order", "amount", "status", "provider", "created_at")
    search_fields = ("reference", "order__id")
    list_filter = ("status", "provider")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "order", "status", "amount", "issued_at")
    search_fields = ("invoice_number",)


@admin.register(TransactionRecord)
class TransactionRecordAdmin(admin.ModelAdmin):
    list_display = ("reference_id", "payment", "transaction_type", "amount", "created_at")


@admin.register(PaymentWebhook)
class PaymentWebhookAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "status", "payment", "created_at")
    list_filter = ("status", "event_type")
