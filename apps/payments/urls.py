from django.urls import path
from .views import (
    PaymentInitializeView,
    PaymentVerifyView,
    InvoiceDetailView,
    InvoiceDownloadView,
    PaystackWebhookView,
)

urlpatterns = [
    path("initialize/", PaymentInitializeView.as_view()),
    path("verify/<str:reference>/", PaymentVerifyView.as_view(), name="payment_verify"),
    path("webhook/", PaystackWebhookView.as_view(), name="paystack_webhook"),
    path("invoices/<int:pk>/", InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/download/", InvoiceDownloadView.as_view(), name="invoice_download"),
]
