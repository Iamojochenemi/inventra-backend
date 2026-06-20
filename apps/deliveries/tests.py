from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.vendors.models import Vendor, VendorStaff
from apps.inventory.models import Product, Category, Inventory
from apps.orders.models import Order
from apps.deliveries.models import Delivery, DeliveryLog
from apps.deliveries.services import create_delivery_from_order

User = get_user_model()


class DeliveryTestCaseBase(APITestCase):
    """Shared fixtures for all delivery tests."""

    @classmethod
    def setUpTestData(cls):

        # ── USERS ──────────────────────────────────────────
        cls.owner_user = User.objects.create_user(
            email="owner@va.com", username="owner_a", password="testpass123",
        )
        cls.dispatcher_user = User.objects.create_user(
            email="dispatch@va.com", username="dispatch_a", password="testpass123",
        )
        cls.rider_user = User.objects.create_user(
            email="rider@va.com", username="rider_a", password="testpass123",
        )
        cls.other_vendor_user = User.objects.create_user(
            email="owner@vb.com", username="owner_b", password="testpass123",
        )

        # ── VENDORS ────────────────────────────────────────
        cls.vendor_a = Vendor.objects.create(owner=cls.owner_user, name="Vendor A")
        cls.vendor_b = Vendor.objects.create(
            owner=cls.other_vendor_user, name="Vendor B"
        )
        cls.branch_a = cls.vendor_a.branches.get(name="Main Branch")
        cls.branch_b = cls.vendor_b.branches.get(name="Main Branch")

        # ── STAFF ──────────────────────────────────────────
        cls.owner_staff = VendorStaff.objects.create(
            vendor=cls.vendor_a, branch=cls.branch_a,
            user=cls.owner_user, role="owner",
        )
        cls.dispatcher_staff = VendorStaff.objects.create(
            vendor=cls.vendor_a, branch=cls.branch_a,
            user=cls.dispatcher_user, role="dispatcher",
        )
        cls.rider_staff = VendorStaff.objects.create(
            vendor=cls.vendor_a, branch=cls.branch_a,
            user=cls.rider_user, role="rider",
        )
        VendorStaff.objects.create(
            vendor=cls.vendor_b, branch=cls.branch_b,
            user=cls.other_vendor_user, role="owner",
        )

        # ── PRODUCTS & INVENTORY ───────────────────────────
        cls.category = Category.objects.create(
            vendor=cls.vendor_a, name="Goods",
        )
        cls.product = Product.objects.create(
            vendor=cls.vendor_a, category=cls.category,
            name="Widget", price=10.00,
        )
        Inventory.objects.create(
            product=cls.product, branch=cls.branch_a, quantity=50,
        )

        # ── ORDERS ─────────────────────────────────────────
        cls.order_a = Order.objects.create(
            vendor=cls.vendor_a, branch=cls.branch_a,
            customer_name="Alice", total_amount=20.00,
            created_by=cls.owner_user, status="confirmed",
        )
        cls.order_b = Order.objects.create(
            vendor=cls.vendor_b, branch=cls.branch_b,
            customer_name="Bob", total_amount=30.00,
            created_by=cls.other_vendor_user, status="confirmed",
        )

        # ── DELIVERIES ─────────────────────────────────────
        cls.delivery_a = create_delivery_from_order(cls.order_a)
        cls.delivery_b = create_delivery_from_order(cls.order_b)

    # ── HELPERS ────────────────────────────────────────────

    def _client(self, user):
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        return client


# =====================================================================
#  DELIVERY LISTING & MULTI-TENANT ISOLATION
# =====================================================================

class DeliveryListTests(DeliveryTestCaseBase):

    def test_list_deliveries_own_vendor(self):
        """User sees only deliveries for their vendor."""
        client = self._client(self.owner_user)
        resp = client.get("/api/deliveries/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [d["id"] for d in resp.data]
        self.assertIn(self.delivery_a.id, ids)
        self.assertNotIn(self.delivery_b.id, ids)

    def test_list_deliveries_vendor_b_isolation(self):
        """Vendor B user sees only B's delivery."""
        client = self._client(self.other_vendor_user)
        resp = client.get("/api/deliveries/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [d["id"] for d in resp.data]
        self.assertIn(self.delivery_b.id, ids)
        self.assertNotIn(self.delivery_a.id, ids)

    def test_list_unauthenticated(self):
        client = APIClient()
        resp = client.get("/api/deliveries/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_own_delivery(self):
        client = self._client(self.owner_user)
        resp = client.get(f"/api/deliveries/{self.delivery_a.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], self.delivery_a.id)

    def test_retrieve_cross_vendor_blocked(self):
        client = self._client(self.other_vendor_user)
        resp = client.get(f"/api/deliveries/{self.delivery_a.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# =====================================================================
#  ASSIGN RIDER
# =====================================================================

class AssignRiderTests(DeliveryTestCaseBase):

    @patch("apps.deliveries.views.create_notification")
    @patch("apps.deliveries.views.create_audit_log")
    def test_dispatcher_can_assign_rider(self, mock_audit, mock_notify):
        """Dispatcher can assign a rider to a pending delivery."""
        client = self._client(self.dispatcher_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/assign_rider/",
            {"rider_id": self.rider_staff.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "assigned")
        self.assertEqual(resp.data["rider_id"], self.rider_staff.id)

        # DB state
        self.delivery_a.refresh_from_db()
        self.assertEqual(self.delivery_a.status, "assigned")
        self.assertEqual(self.delivery_a.assigned_rider_id, self.rider_staff.id)

    @patch("apps.deliveries.views.create_notification")
    @patch("apps.deliveries.views.create_audit_log")
    def test_assign_rider_creates_delivery_log(self, mock_audit, mock_notify):
        """assign_rider should create a DeliveryLog entry."""
        client = self._client(self.dispatcher_user)
        client.post(
            f"/api/deliveries/{self.delivery_a.id}/assign_rider/",
            {"rider_id": self.rider_staff.id},
            format="json",
        )
        self.assertTrue(
            DeliveryLog.objects.filter(
                delivery=self.delivery_a,
                event_type="rider_assignment",
            ).exists()
        )

    def test_owner_cannot_assign_rider(self):
        """Owner role (not dispatcher) gets 403."""
        client = self._client(self.owner_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/assign_rider/",
            {"rider_id": self.rider_staff.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_rider_cannot_assign_rider(self):
        """Rider role cannot assign riders."""
        client = self._client(self.rider_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/assign_rider/",
            {"rider_id": self.rider_staff.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_assign_rider_cross_vendor_blocked(self):
        """User from Vendor B cannot assign rider to Vendor A delivery."""
        client = self._client(self.other_vendor_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/assign_rider/",
            {"rider_id": self.rider_staff.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_assign_nonexistent_rider(self):
        client = self._client(self.dispatcher_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/assign_rider/",
            {"rider_id": 99999},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# =====================================================================
#  UPDATE DELIVERY STATUS
# =====================================================================

class UpdateDeliveryStatusTests(DeliveryTestCaseBase):

    def setUp(self):
        super().setUp()
        # Pre-assign rider so delivery is in "assigned" state
        self.delivery_a.assigned_rider = self.rider_staff
        self.delivery_a.status = "assigned"
        self.delivery_a.save()

    @patch("apps.deliveries.views.create_notification")
    @patch("apps.deliveries.views.create_audit_log")
    def test_rider_can_update_to_picked_up(self, mock_audit, mock_notify):
        """Rider can transition assigned → picked_up."""
        client = self._client(self.rider_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/update_status/",
            {"status": "picked_up"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.delivery_a.refresh_from_db()
        self.assertEqual(self.delivery_a.status, "picked_up")

    @patch("apps.deliveries.views.create_notification")
    @patch("apps.deliveries.views.create_audit_log")
    def test_rider_can_update_to_in_transit(self, mock_audit, mock_notify):
        """Rider can transition picked_up → in_transit."""
        self.delivery_a.status = "picked_up"
        self.delivery_a.save()
        client = self._client(self.rider_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/update_status/",
            {"status": "in_transit"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.delivery_a.refresh_from_db()
        self.assertEqual(self.delivery_a.status, "in_transit")

    @patch("apps.deliveries.views.create_notification")
    @patch("apps.deliveries.views.create_audit_log")
    def test_rider_can_mark_delivered(self, mock_audit, mock_notify):
        """Rider can transition in_transit → delivered with recipient name."""
        self.delivery_a.status = "in_transit"
        self.delivery_a.save()
        client = self._client(self.rider_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/update_status/",
            {"status": "delivered", "recipient_name": "Alice Smith"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.delivery_a.refresh_from_db()
        self.assertEqual(self.delivery_a.status, "delivered")
        self.assertEqual(self.delivery_a.recipient_name, "Alice Smith")
        self.assertIsNotNone(self.delivery_a.delivered_at)

    @patch("apps.deliveries.views.create_notification")
    @patch("apps.deliveries.views.create_audit_log")
    def test_status_update_creates_delivery_log(self, mock_audit, mock_notify):
        """Status change creates a DeliveryLog entry."""
        client = self._client(self.rider_user)
        client.post(
            f"/api/deliveries/{self.delivery_a.id}/update_status/",
            {"status": "picked_up"},
            format="json",
        )
        self.assertTrue(
            DeliveryLog.objects.filter(
                delivery=self.delivery_a,
                event_type="status_change",
                previous_value="assigned",
                new_value="picked_up",
            ).exists()
        )

    def test_owner_cannot_update_status(self):
        """Non-rider gets 403."""
        client = self._client(self.owner_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/update_status/",
            {"status": "picked_up"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_dispatcher_cannot_update_status(self):
        client = self._client(self.dispatcher_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/update_status/",
            {"status": "picked_up"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_transition_returns_400(self):
        """assigned → delivered (skipping picked_up, in_transit) is rejected."""
        client = self._client(self.rider_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/update_status/",
            {"status": "delivered"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot change from", str(resp.data))

    def test_invalid_status_value_returns_400(self):
        client = self._client(self.rider_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/update_status/",
            {"status": "nonexistent"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cross_vendor_cannot_update_status(self):
        client = self._client(self.other_vendor_user)
        resp = client.post(
            f"/api/deliveries/{self.delivery_a.id}/update_status/",
            {"status": "picked_up"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# =====================================================================
#  DELIVERY CREATION & IDEMPOTENCY
# =====================================================================

class DeliveryCreationTests(DeliveryTestCaseBase):

    def test_create_delivery_from_confirmed_order(self):
        """create_delivery_from_order returns a pending delivery."""
        delivery = create_delivery_from_order(self.order_a)
        self.assertIsNotNone(delivery)
        self.assertEqual(delivery.status, "pending")
        self.assertEqual(delivery.order, self.order_a)

    def test_create_delivery_is_idempotent(self):
        """Calling create_delivery_from_order twice returns same delivery."""
        first = create_delivery_from_order(self.order_a)
        second = create_delivery_from_order(self.order_a)
        self.assertEqual(first.id, second.id)

    def test_create_delivery_for_none_order(self):
        """Passing None returns None."""
        self.assertIsNone(create_delivery_from_order(None))
