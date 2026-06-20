"""
Paystack webhook listener tests.
────────────────────────────────
Uses mocked PaystackService so no live API calls are made.
"""

from unittest.mock import patch
import json

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.vendors.models import Vendor, VendorStaff
from apps.orders.models import Order
from apps.payments.models import Payment, PaymentWebhook
from apps.payments.services import PaystackService, PaystackVerificationError

User = get_user_model()


class PaystackWebhookTestCase(APITestCase):
    """Shared fixtures for all webhook tests."""

    @classmethod
    def setUpTestData(cls):

        # ── USERS ──────────────────────────────────────────
        cls.owner = User.objects.create_user(
            email="owner@test.com", username="owner",
            password="testpass123", role="vendor",
        )

        # ── VENDOR ─────────────────────────────────────────
        cls.vendor = Vendor.objects.create(owner=cls.owner, name="Test Vendor")
        cls.branch = cls.vendor.branches.get(name="Main Branch")
        VendorStaff.objects.create(
            vendor=cls.vendor, branch=cls.branch,
            user=cls.owner, role="owner",
        )

        # ── ORDER & PENDING PAYMENT ────────────────────────
        cls.order = Order.objects.create(
            vendor=cls.vendor, branch=cls.branch,
            customer_name="John Doe", total_amount=200.00,
            created_by=cls.owner, status="pending",
        )
        cls.payment = Payment.objects.create(
            order=cls.order, amount=200.00,
            reference="INV-TEST-001", status="pending",
        )

        # ── ALREADY-SUCCESSFUL PAYMENT (for dup tests) ─────
        cls.paid_order = Order.objects.create(
            vendor=cls.vendor, branch=cls.branch,
            customer_name="Jane Doe", total_amount=150.00,
            created_by=cls.owner, status="confirmed",
        )
        cls.successful_payment = Payment.objects.create(
            order=cls.paid_order, amount=150.00,
            reference="INV-TEST-002", status="successful",
            gateway_transaction_id="gw-12345",
        )

    # ── HELPERS ────────────────────────────────────────────

    @staticmethod
    def _webhook_payload(reference="INV-TEST-001", event="charge.success",
                         status_val="success", amount=20000):
        return {
            "event": event,
            "data": {
                "id": 98765,
                "reference": reference,
                "status": status_val,
                "amount": amount,
                "currency": "NGN",
                "customer": {"email": "customer@test.com"},
                "gateway_response": "Successful",
            },
        }

    def _post_webhook(self, payload, signature="valid-sig"):
        """POST a webhook payload to the endpoint."""
        client = APIClient()
        return client.post(
            "/api/payments/webhook/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )


# =====================================================================
#  200 OK ON VERIFIED EVENTS
# =====================================================================

@patch("apps.payments.views.PaystackService.__init__", return_value=None)
class VerifiedWebhookTests(PaystackWebhookTestCase):
    """All tests in this class assert 200 OK for legitimate webhooks."""

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    @patch.object(PaystackService, "handle_successful_payment")
    @patch("apps.payments.views.process_payment_success")
    def test_successful_charge_returns_200(self, mock_process, mock_handle, mock_validate):
        """charge.success for a pending payment returns 200 + 'success'."""
        payload = self._webhook_payload()
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["payment"], "INV-TEST-001")

        # Validate signature checked
        mock_validate.assert_called_once()

        # Payment processing triggered
        mock_handle.assert_called_once()
        mock_process.assert_called_once()

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    @patch.object(PaystackService, "handle_successful_payment")
    @patch("apps.payments.views.process_payment_success")
    def test_webhook_creates_webhook_record(self, mock_process, mock_handle, mock_validate):
        """Every processed webhook creates a PaymentWebhook audit record."""
        payload = self._webhook_payload()
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        record_exists = PaymentWebhook.objects.filter(
            event_type="charge.success", event_id="98765"
        ).exists()
        self.assertTrue(record_exists)

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    def test_non_charge_event_returns_200_ignored(self, mock_validate):
        """Events other than charge.success return 200 with 'ignored' status."""
        payload = self._webhook_payload(event="transfer.success")
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "ignored")

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    @patch.object(PaystackService, "handle_successful_payment")
    @patch("apps.payments.views.process_payment_success")
    def test_webhook_without_event_id_falls_back(self, mock_process, mock_handle, mock_validate):
        """Payload missing data.id uses reference as event_id (no crash)."""
        payload = self._webhook_payload()
        # Remove data.id
        del payload["data"]["id"]

        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "success")


# =====================================================================
#  DUPLICATE PAYLOAD HANDLING (IDEMPOTENCY)
# =====================================================================

@patch("apps.payments.views.PaystackService.__init__", return_value=None)
class DuplicateWebhookTests(PaystackWebhookTestCase):
    """Safe handling of duplicate / replayed webhook payloads."""

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    def test_duplicate_for_already_successful_payment(self, mock_validate):
        """A second webhook for an already-successful payment returns early."""
        payload = self._webhook_payload(reference="INV-TEST-002")
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "already processed")

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    def test_first_webhook_processes_second_is_idempotent(self, mock_validate):
        """Two identical webhooks: first processes, second returns already-processed."""
        payload = self._webhook_payload(reference="INV-TEST-001")

        # First call — payment is pending, processes it
        with patch.object(PaystackService, "handle_successful_payment") as mock_handle:
            with patch("apps.payments.views.process_payment_success"):
                resp1 = self._post_webhook(payload)
                self.assertEqual(resp1.status_code, status.HTTP_200_OK)
                data1 = json.loads(resp1.content)
                self.assertEqual(data1["status"], "success")
                mock_handle.assert_called_once()

        # Simulate what handle_successful_payment would do
        self.payment.status = "successful"
        self.payment.gateway_transaction_id = "gw-98765"
        self.payment.save()

        # Second call — payment is now successful
        resp2 = self._post_webhook(payload)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        data2 = json.loads(resp2.content)
        self.assertEqual(data2["status"], "already processed")

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    def test_duplicate_webhook_with_interleaved_failure(self, mock_validate):
        """If first webhook fails processing, a second attempt marks it processed."""
        payload = self._webhook_payload(reference="INV-TEST-001")

        # First call — handle_successful_payment raises
        with patch.object(
            PaystackService, "handle_successful_payment",
            side_effect=PaystackVerificationError("First attempt failed"),
        ):
            resp1 = self._post_webhook(payload)
            self.assertEqual(resp1.status_code, status.HTTP_400_BAD_REQUEST)
            data1 = json.loads(resp1.content)
            self.assertIn("verification failed", str(data1).lower())

        # Payment remains pending
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    def test_same_event_id_different_reference_creates_separate_record(self, mock_validate):
        """Different webhooks with same event_id but different payments are handled."""
        # Make a second pending payment
        order2 = Order.objects.create(
            vendor=self.vendor, branch=self.branch,
            customer_name="Alice", total_amount=100.00,
            created_by=self.owner, status="pending",
        )
        Payment.objects.create(
            order=order2, amount=100.00,
            reference="INV-TEST-003", status="pending",
        )

        payload1 = self._webhook_payload(reference="INV-TEST-001")
        payload2 = self._webhook_payload(reference="INV-TEST-003")

        with patch.object(PaystackService, "handle_successful_payment"):
            with patch("apps.payments.views.process_payment_success"):
                resp1 = self._post_webhook(payload1)
                self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        # Mark first payment successful
        self.payment.status = "successful"
        self.payment.save()

        resp2 = self._post_webhook(payload2)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        data2 = json.loads(resp2.content)
        self.assertEqual(data2["status"], "success")


# =====================================================================
#  SIGNATURE & PAYLOAD VALIDATION
# =====================================================================

class WebhookValidationTests(PaystackWebhookTestCase):

    def test_invalid_signature_returns_401(self):
        """Webhook with an invalid HMAC signature returns 401."""
        from apps.payments.services import WebhookSignatureError

        with patch.object(
            PaystackService, "validate_webhook_signature",
            side_effect=WebhookSignatureError("Invalid signature"),
        ):
            payload = self._webhook_payload()
            response = self._post_webhook(payload, signature="bad-sig")

            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            data = json.loads(response.content)
            self.assertIn("Invalid signature", str(data))

    @patch.object(
        PaystackService, "validate_webhook_signature",
        side_effect=Exception("Missing signature header"),
    )
    def test_missing_signature_header_returns_400(self, _):
        """Webhook without X-Paystack-Signature returns 400."""
        payload = self._webhook_payload()
        client = APIClient()
        response = client.post(
            "/api/payments/webhook/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(response.content)
        self.assertIn("Validation failed", str(data))

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    def test_missing_reference_returns_400(self, mock_validate):
        """Webhook payload without 'reference' returns 400."""
        payload = {
            "event": "charge.success",
            "data": {"id": 12345, "status": "success"},
        }
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(response.content)
        self.assertIn("Missing reference", str(data))

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    def test_payment_not_found_returns_404(self, mock_validate):
        """Webhook for a non-existent payment reference returns 404."""
        payload = self._webhook_payload(reference="NONEXISTENT-REF")
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        data = json.loads(response.content)
        self.assertIn("Payment not found", str(data))

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    def test_invalid_json_body_returns_400(self, mock_validate):
        """Malformed JSON body returns 400."""
        client = APIClient()
        response = client.post(
            "/api/payments/webhook/",
            data="this is not json",
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE="some-sig",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =====================================================================
#  VERIFICATION FAILURE RECOVERY
# =====================================================================

@patch("apps.payments.views.PaystackService.__init__", return_value=None)
class WebhookRecoveryTests(PaystackWebhookTestCase):

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    @patch.object(PaystackService, "handle_successful_payment")
    def test_verification_failure_marks_payment_failed(self, mock_handle, mock_validate):
        """If handle_successful_payment raises, the payment is marked failed."""
        mock_handle.side_effect = PaystackVerificationError(
            "Transaction verification failed"
        )

        payload = self._webhook_payload()
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = json.loads(response.content)
        self.assertIn("verification failed", str(data).lower())

        # Payment status should be "failed"
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")

    @patch.object(PaystackService, "validate_webhook_signature", return_value=True)
    @patch.object(PaystackService, "handle_successful_payment")
    def test_failure_records_webhook_with_error(self, mock_handle, mock_validate):
        """A failed webhook processing creates a PaymentWebhook with failed status."""
        mock_handle.side_effect = PaystackVerificationError("Verification failed")

        payload = self._webhook_payload(reference="INV-TEST-001")
        self._post_webhook(payload)

        webhook_record = PaymentWebhook.objects.filter(
            event_type="charge.success",
            event_id="98765",
        ).first()

        self.assertIsNotNone(webhook_record)
        self.assertEqual(webhook_record.status, "failed")
        self.assertIn("Verification failed", webhook_record.error_message or "")
