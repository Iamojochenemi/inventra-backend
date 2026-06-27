import json
import logging

from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.mixins import TenantIsolationMixin
from apps.vendors.services import validate_vendor_access

from .models import Invoice, Payment
from .serializers import PaymentInitializeSerializer
from .services import (
    PaystackService,
    PaystackVerificationError,
    WebhookSignatureError,
    process_payment_success,
    record_payment_webhook,
)

logger = logging.getLogger(__name__)


def _get_client_meta(request):
    ip_address = request.META.get("REMOTE_ADDR")
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return ip_address, user_agent


# -------------------------
# PAYMENT INITIALIZATION
# -------------------------
@extend_schema(
    tags=["Payments"],
    summary="Initialize payment",
    description="Initialize a Paystack payment transaction for an order.",
    request=PaymentInitializeSerializer,
    responses={
        201: OpenApiResponse(description="Payment initialized with authorization URL"),
        400: OpenApiResponse(
            description="Validation error or payment initialization failed"
        ),
    },
)
class PaymentInitializeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PaymentInitializeSerializer(data=request.data)

        if serializer.is_valid():
            payment = serializer.save()
            order = payment.order

            validate_vendor_access(
                vendor=order.vendor,
                user=request.user,
                allowed_roles=["owner", "manager"],
            )

            try:
                paystack_service = PaystackService()
                amount_in_kobo = int(payment.amount * 100)

                if not payment.order.created_by:
                    raise ValueError("Order has no associated user for payment")
                customer_email = payment.order.created_by.email

                transaction_data = paystack_service.initialize_transaction(
                    amount=amount_in_kobo,
                    email=customer_email,
                    reference=payment.reference,
                    order_id=payment.order.id,
                )

                logger.info(f"Transaction initialized for payment {payment.reference}")

                return Response(
                    {
                        "reference": payment.reference,
                        "amount": payment.amount,
                        "currency": payment.currency,
                        "status": payment.status,
                        "authorization_url": transaction_data.get("authorization_url"),
                        "access_code": transaction_data.get("access_code"),
                    },
                    status=status.HTTP_201_CREATED,
                )

            except Exception as e:
                logger.error(f"Failed to initialize transaction: {str(e)}")
                return Response(
                    {
                        "error": "Failed to initialize payment",
                        "details": str(e),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# -------------------------
# PAYSTACK WEBHOOK
# -------------------------


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(exclude=True)
class PaystackWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        ip_address, user_agent = _get_client_meta(request)

        try:
            paystack_service = PaystackService()
            signature_header = request.META.get("HTTP_X_PAYSTACK_SIGNATURE")

            paystack_service.validate_webhook_signature(
                request.body,
                signature_header,
            )

        except WebhookSignatureError as e:
            logger.error(f"Webhook signature validation failed: {str(e)}")
            return JsonResponse({"error": "Invalid signature"}, status=401)
        except Exception as e:
            logger.error(f"Webhook validation error: {str(e)}")
            return JsonResponse({"error": "Validation failed"}, status=400)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        event = payload.get("event")
        data = payload.get("data", {})
        event_id = (
            data.get("id") or payload.get("id") or data.get("reference", "unknown")
        )

        if event != "charge.success":
            logger.info(f"Ignoring webhook event: {event}")
            record_payment_webhook(event, str(event_id), payload, status="processed")
            return JsonResponse({"status": "ignored"})

        reference = data.get("reference")

        if not reference:
            logger.warning("Webhook received without reference")
            return JsonResponse({"error": "Missing reference"}, status=400)

        try:
            payment = Payment.objects.select_related("order").get(reference=reference)
        except Payment.DoesNotExist:
            logger.error(f"Payment not found for reference: {reference}")
            record_payment_webhook(
                event,
                str(event_id),
                payload,
                status="failed",
                error_message="Payment not found",
            )
            return JsonResponse({"error": "Payment not found"}, status=404)

        if payment.status == "successful":
            logger.info(f"Payment {reference} already processed")
            record_payment_webhook(event, str(event_id), payload, payment=payment)
            return JsonResponse({"status": "already processed"})

        try:
            paystack_service = PaystackService()
            paystack_service.handle_successful_payment(reference, payment)

            process_payment_success(
                payment,
                user=payment.order.created_by,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            record_payment_webhook(event, str(event_id), payload, payment=payment)

            logger.info(
                f"Payment {reference} processed successfully for order {payment.order.id}"
            )

            return JsonResponse(
                {
                    "status": "success",
                    "payment": payment.reference,
                    "order_id": payment.order.id,
                }
            )

        except PaystackVerificationError as e:
            logger.error(f"Payment verification failed for {reference}: {str(e)}")
            paystack_service.handle_failed_payment(
                reference,
                payment,
                reason=str(e),
            )
            record_payment_webhook(
                event,
                str(event_id),
                payload,
                payment=payment,
                status="failed",
                error_message=str(e),
            )
            return JsonResponse(
                {
                    "error": "Payment verification failed",
                    "details": str(e),
                },
                status=400,
            )
        except Exception as e:
            logger.error(f"Webhook processing error for {reference}: {str(e)}")
            record_payment_webhook(
                event,
                str(event_id),
                payload,
                payment=payment,
                status="failed",
                error_message=str(e),
            )
            return JsonResponse(
                {
                    "error": "Processing failed",
                    "details": str(e),
                },
                status=500,
            )


# -------------------------
# PAYMENT VERIFICATION
# -------------------------
@extend_schema(
    tags=["Payments"],
    summary="Verify payment",
    description="Verify a Paystack transaction and update the payment status.",
    responses={
        200: OpenApiResponse(description="Payment verification result"),
        400: OpenApiResponse(description="Verification failed"),
        404: OpenApiResponse(description="Payment not found"),
    },
)
class PaymentVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, reference):
        try:
            payment = Payment.objects.select_related("order").get(reference=reference)
        except Payment.DoesNotExist:
            logger.error(f"Payment not found for verification: {reference}")
            return Response(
                {"error": "Payment not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        validate_vendor_access(
            vendor=payment.order.vendor,
            user=request.user,
            allowed_roles=["owner", "manager"],
        )

        ip_address, user_agent = _get_client_meta(request)

        try:
            paystack_service = PaystackService()
            verification_result = paystack_service.verify_transaction(reference)

            transaction_status = verification_result.get("status")

            if transaction_status == "success" and payment.status != "successful":
                paystack_service.handle_successful_payment(reference, payment)
                process_payment_success(
                    payment,
                    user=request.user,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                logger.info(f"Payment {reference} verified and updated to successful")

            elif transaction_status == "failed" and payment.status != "failed":
                paystack_service.handle_failed_payment(
                    reference,
                    payment,
                    reason="Transaction failed at gateway",
                )
                logger.info(f"Payment {reference} verified and marked as failed")

            return Response(
                {
                    "reference": payment.reference,
                    "amount": payment.amount,
                    "currency": payment.currency,
                    "status": payment.status,
                    "gateway_status": transaction_status,
                    "gateway_transaction_id": verification_result.get(
                        "gateway_transaction_id"
                    ),
                    "customer_email": verification_result.get("customer_email"),
                },
                status=status.HTTP_200_OK,
            )

        except PaystackVerificationError as e:
            logger.error(f"Verification failed for {reference}: {str(e)}")
            return Response(
                {
                    "error": "Verification failed",
                    "details": str(e),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Unexpected error verifying {reference}: {str(e)}")
            return Response(
                {
                    "error": "Verification error",
                    "details": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["Invoices"],
    summary="Retrieve invoice",
    description="Retrieve invoice details by ID.",
    responses={
        200: OpenApiResponse(description="Invoice details"),
        404: OpenApiResponse(description="Invoice not found"),
    },
)
class InvoiceDetailView(TenantIsolationMixin, APIView):
    tenant_vendor_field = "order__vendor"
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        invoice = get_object_or_404(
            self.scope_queryset(
                Invoice.objects.select_related("order", "order__vendor"),
            ),
            pk=pk,
        )
        return Response(
            {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "status": invoice.status,
                "amount": invoice.amount,
                "currency": invoice.currency,
                "issued_at": invoice.issued_at,
                "due_date": invoice.due_date,
                "paid_at": invoice.paid_at,
                "order_id": invoice.order_id,
                "pdf_url": invoice.pdf_file.url if invoice.pdf_file else None,
            }
        )


@extend_schema(
    tags=["Invoices"],
    summary="Download invoice PDF",
    description="Download the invoice PDF file as an attachment.",
    responses={
        200: OpenApiResponse(description="PDF file download"),
        404: OpenApiResponse(description="Invoice not found"),
    },
)
class InvoiceDownloadView(TenantIsolationMixin, APIView):
    tenant_vendor_field = "order__vendor"
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        invoice = get_object_or_404(
            self.scope_queryset(
                Invoice.objects.select_related("order", "order__vendor"),
            ),
            pk=pk,
        )

        if not invoice.pdf_file:
            from apps.payments.services.invoice_service import save_invoice_pdf

            save_invoice_pdf(invoice)

        return FileResponse(
            invoice.pdf_file.open("rb"),
            as_attachment=True,
            filename=f"{invoice.invoice_number}.pdf",
        )
