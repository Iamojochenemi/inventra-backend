from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from .views import (
    PaymentInitializeView,
    PaymentVerifyView,
    InvoiceDetailView,
    InvoiceDownloadView,
    paystack_webhook,
)

urlpatterns = [
    path("initialize/", PaymentInitializeView.as_view()),
    path("verify/<str:reference>/", PaymentVerifyView.as_view(), name="payment_verify"),
    path("webhook/", csrf_exempt(paystack_webhook), name="paystack_webhook"),
    path("invoices/<int:pk>/", InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/download/", InvoiceDownloadView.as_view(), name="invoice_download"),
]
