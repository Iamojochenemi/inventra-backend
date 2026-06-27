import hashlib
import hmac
import logging
import uuid
from decimal import Decimal

import requests
from django.conf import settings

from .models import Payment

logger = logging.getLogger(__name__)


def generate_reference():
    return f"INV-{uuid.uuid4().hex[:10].upper()}"


def create_payment_for_order(order):
    """
    STRICT: One payment per order (idempotent)
    """

    # -------------------------
    # 1. RETURN EXISTING PAYMENT
    # -------------------------
    payment = Payment.objects.filter(order=order).first()

    if payment:
        # Always sync amount (order may change)
        if payment.amount != order.total_amount:
            payment.amount = order.total_amount
            payment = create_payment_for_order(payment.order).save(
                update_fields=["amount"]
            )

        return payment

    # -------------------------
    # 2. CREATE NEW PAYMENT
    # -------------------------
    payment = Payment.objects.create(
        order=order,
        amount=order.total_amount,
        reference=f"INV-{order.id}",  # stable + deterministic
        status="pending",
    )

    return payment


# -------------------------
# PAYSTACK SERVICE
# -------------------------
class PaystackException(Exception):
    """Base exception for Paystack service errors"""

    pass


class PaystackVerificationError(PaystackException):
    """Exception raised when transaction verification fails"""

    pass


class WebhookSignatureError(PaystackException):
    """Exception raised when webhook signature validation fails"""

    pass


class PaystackService:
    """Service for integrating with Paystack payment gateway"""

    BASE_URL = "https://api.paystack.co"
    TIMEOUT = 10  # seconds

    def __init__(self, api_key=None):
        """
        Initialize PaystackService with API credentials.

        Args:
            api_key (str, optional): Paystack secret key. If not provided,
                                    loads from Django settings.

        Raises:
            PaystackException: If API key is not provided and not in settings.
        """
        self.api_key = api_key or getattr(settings, "PAYSTACK_SECRET_KEY", None)

        if not self.api_key:
            raise PaystackException(
                "Paystack API key not provided. Set PAYSTACK_SECRET_KEY in settings."
            )

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _make_request(self, method, endpoint, **kwargs):
        """
        Make HTTP request to Paystack API with error handling.

        Args:
            method (str): HTTP method (GET, POST, etc.)
            endpoint (str): API endpoint path (e.g., '/transaction/initialize')
            **kwargs: Additional arguments passed to requests

        Returns:
            dict: Parsed JSON response

        Raises:
            PaystackException: If request fails or returns error
        """
        url = f"{self.BASE_URL}{endpoint}"
        kwargs.setdefault("headers", self.headers)
        kwargs.setdefault("timeout", self.TIMEOUT)

        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()

            data = response.json()

            if not data.get("status"):
                raise PaystackException(
                    f"Paystack API error: {data.get('message', 'Unknown error')}"
                )

            return data

        except requests.exceptions.Timeout:
            logger.error(f"Paystack API timeout: {endpoint}")
            raise PaystackException("Paystack API request timed out")

        except requests.exceptions.ConnectionError:
            logger.error(f"Paystack API connection error: {endpoint}")
            raise PaystackException("Failed to connect to Paystack API")

        except requests.exceptions.HTTPError as e:
            logger.error(
                f"Paystack API HTTP error: {endpoint} - {e.response.status_code}"
            )
            raise PaystackException(f"Paystack API error: {e.response.status_code}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack API request error: {endpoint} - {str(e)}")
            raise PaystackException(f"Paystack API request failed: {str(e)}")

    def initialize_transaction(self, amount, email, reference, order_id=None):
        """
        Initialize a transaction on Paystack.

        Args:
            amount (int or Decimal): Amount in kobo (smallest currency unit)
            email (str): Customer email address
            reference (str): Unique payment reference
            order_id (int, optional): Associated order ID for tracking

        Returns:
            dict: Contains 'authorization_url', 'access_code', 'reference'

        Raises:
            PaystackException: If initialization fails

        Example:
            >>> service = PaystackService()
            >>> result = service.initialize_transaction(
            ...     amount=50000,  # ₦500.00
            ...     email='customer@example.com',
            ...     reference='INV-ABC123'
            ... )
            >>> print(result['authorization_url'])
        """
        if not isinstance(amount, (int, Decimal)):
            raise PaystackException("Amount must be an integer (in kobo)")

        if amount <= 0:
            raise PaystackException("Amount must be greater than 0")

        payload = {
            "amount": int(amount),
            "email": email,
            "reference": reference,
        }

        # Add metadata for tracking
        if order_id:
            payload["metadata"] = {"order_id": order_id}

        try:
            logger.info(f"Initializing Paystack transaction: {reference}")
            response = self._make_request(
                "POST",
                "/transaction/initialize",
                json=payload,
            )

            data = response.get("data", {})

            return {
                "authorization_url": data.get("authorization_url"),
                "access_code": data.get("access_code"),
                "reference": data.get("reference"),
            }

        except PaystackException as e:
            logger.error(f"Failed to initialize transaction {reference}: {e}")
            raise

    def verify_transaction(self, reference):
        """
        Verify a transaction with Paystack.

        Args:
            reference (str): The transaction reference to verify

        Returns:
            dict: Contains 'status', 'amount', 'gateway_transaction_id',
                  'customer_email', 'raw_response'

        Raises:
            PaystackVerificationError: If verification fails

        Example:
            >>> service = PaystackService()
            >>> result = service.verify_transaction('INV-ABC123')
            >>> if result['status'] == 'success':
            ...     print(f"Payment of {result['amount']} received")
        """
        try:
            logger.info(f"Verifying Paystack transaction: {reference}")
            response = self._make_request(
                "GET",
                f"/transaction/verify/{reference}",
            )

            data = response.get("data", {})

            # Extract key information
            verification_result = {
                "status": data.get("status"),  # success, failed, abandoned
                "amount": data.get("amount"),  # in kobo
                "gateway_transaction_id": data.get("id"),
                "customer_email": data.get("customer", {}).get("email"),
                "payment_method": data.get("authorization", {}).get(
                    "authorization_code"
                ),
                "raw_response": data,
            }

            return verification_result

        except PaystackException as e:
            logger.error(f"Failed to verify transaction {reference}: {e}")
            raise PaystackVerificationError(
                f"Transaction verification failed: {str(e)}"
            )

    def get_transaction_details(self, reference):
        """
        Fetch detailed information about a transaction.

        Args:
            reference (str): The transaction reference

        Returns:
            dict: Complete transaction details from Paystack

        Raises:
            PaystackException: If retrieval fails
        """
        return self._make_request(
            "GET",
            f"/transaction/{reference}",
        ).get("data", {})

    def validate_webhook_signature(self, payload_body, signature_header):
        """
        Validate Paystack webhook signature for security.

        Args:
            payload_body (bytes): Raw request body from webhook
            signature_header (str): X-Paystack-Signature header value

        Returns:
            bool: True if signature is valid

        Raises:
            WebhookSignatureError: If signature is invalid

        Example:
            >>> service = PaystackService()
            >>> is_valid = service.validate_webhook_signature(
            ...     request.body,
            ...     request.META.get('HTTP_X_PAYSTACK_SIGNATURE')
            ... )
        """
        if not signature_header:
            raise WebhookSignatureError("Missing signature header")

        hash_object = hmac.new(
            self.api_key.encode("utf-8"),
            payload_body,
            hashlib.sha512,
        )
        computed_signature = hash_object.hexdigest()

        if not hmac.compare_digest(computed_signature, signature_header):
            logger.warning("Webhook signature validation failed - possible tampering")
            raise WebhookSignatureError("Invalid webhook signature")

        logger.info("Webhook signature validated successfully")
        return True

    def handle_successful_payment(self, reference, payment_instance):
        """
        Process a successful payment and update Payment model.

        Args:
            reference (str): The transaction reference
            payment_instance (Payment): Payment model instance to update

        Returns:
            Payment: Updated payment instance

        Raises:
            PaystackVerificationError: If verification fails
        """
        verification = self.verify_transaction(reference)

        if verification["status"] != "success":
            raise PaystackVerificationError(
                f"Transaction status is {verification['status']}, not success"
            )

        # Update payment record
        payment_instance.status = "successful"
        payment_instance.gateway_transaction_id = verification["gateway_transaction_id"]
        payment_instance.raw_response = verification["raw_response"]
        payment_instance.save()

        logger.info(
            f"Payment {reference} marked as successful with "
            f"gateway ID: {verification['gateway_transaction_id']}"
        )

        return payment_instance

    def handle_failed_payment(self, reference, payment_instance, reason=None):
        """
        Process a failed payment and update Payment model.

        Args:
            reference (str): The transaction reference
            payment_instance (Payment): Payment model instance to update
            reason (str, optional): Reason for failure

        Returns:
            Payment: Updated payment instance
        """
        payment_instance.status = "failed"
        payment_instance.failure_reason = reason or "Payment failed at gateway"
        payment_instance.save()

        logger.warning(f"Payment {reference} marked as failed: {reason}")

        return payment_instance


def process_payment_success(payment, user=None, ip_address=None, user_agent=None):
    """
    Idempotent payment success processor (SAFE TO RUN MULTIPLE TIMES)
    """

    from django.db import transaction

    from apps.audit_logs.services import create_audit_log
    from apps.deliveries.services import create_delivery_from_order
    from apps.orders.models import OrderStatusLog
    from apps.payments.models import TransactionRecord
    from apps.payments.services.invoice_service import (
        create_invoice_from_order,
        mark_invoice_as_paid,
    )
    from apps.payments.tasks import generate_invoice_pdf_task

    order = payment.order

    with transaction.atomic():
        # --------------------------
        # 1. ORDER STATUS (SAFE CHECK)
        # --------------------------
        old_status = order.status

        if order.status != "confirmed":
            order.status = "confirmed"
            order.save(update_fields=["status"])

            OrderStatusLog.objects.create(
                order=order,
                previous_status=old_status,
                new_status="confirmed",
                changed_by=user or order.created_by,
            )

        # --------------------------
        # 2. DELIVERY (IDEMPOTENT)
        # --------------------------
        if not hasattr(order, "delivery"):
            create_delivery_from_order(order)

        # --------------------------
        # 3. INVOICE (IDEMPOTENT)
        # --------------------------
        if hasattr(order, "invoice"):
            invoice = order.invoice
        else:
            invoice = create_invoice_from_order(order)

        if invoice.status != "paid":
            mark_invoice_as_paid(invoice)

        # --------------------------
        # 4. TRANSACTION RECORD (NO DUPLICATES)
        # --------------------------
        if payment.gateway_transaction_id:
            TransactionRecord.objects.get_or_create(
                payment=payment,
                reference_id=str(payment.gateway_transaction_id),
                defaults={
                    "transaction_type": "payment",
                    "amount": payment.amount,
                    "description": f"Payment for order #{order.id}",
                    "raw_data": payment.raw_response,
                },
            )

        # --------------------------
        # 5. INVOICE PDF (ASYNC)
        # --------------------------
        generate_invoice_pdf_task.delay(invoice.id)

        # --------------------------
        # 6. AUDIT LOG (SAFE)
        # --------------------------
        create_audit_log(
            user=user or order.created_by,
            obj=order,
            action="update",
            old_values={"status": old_status},
            new_values={"status": "confirmed"},
            ip_address=ip_address,
            user_agent=user_agent,
            reason="Payment successful",
        )

    return payment


def record_payment_webhook(
    event_type, event_id, payload, payment=None, status="processed", error_message=None
):
    from django.utils import timezone

    from apps.payments.models import PaymentWebhook

    webhook, _ = PaymentWebhook.objects.update_or_create(
        event_id=event_id,
        defaults={
            "payment": payment,
            "event_type": event_type,
            "status": status,
            "payload": payload,
            "error_message": error_message,
            "processed_at": timezone.now() if status == "processed" else None,
        },
    )
    return webhook
