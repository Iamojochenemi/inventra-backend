from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.inventory.models import Category, Inventory, Product
from apps.orders.models import Order, OrderStatusLog
from apps.vendors.models import Vendor, VendorStaff

User = get_user_model()


class OrderTestCaseBase(APITestCase):
    """Base class with shared fixtures for all order tests."""

    @classmethod
    def setUpTestData(cls):

        # ── USERS ──────────────────────────────────────────
        cls.owner_user = User.objects.create_user(
            email="owner@vendor_a.com",
            username="owner_a",
            password="testpass123",
            role="vendor",
        )
        cls.manager_user = User.objects.create_user(
            email="manager@vendor_a.com",
            username="manager_a",
            password="testpass123",
            role="vendor",
        )
        cls.other_vendor_user = User.objects.create_user(
            email="owner@vendor_b.com",
            username="owner_b",
            password="testpass123",
            role="vendor",
        )
        cls.unaffiliated_user = User.objects.create_user(
            email="stranger@example.com",
            username="stranger",
            password="testpass123",
            role="staff",
        )

        # ── VENDORS ────────────────────────────────────────
        cls.vendor_a = Vendor.objects.create(
            owner=cls.owner_user,
            name="Vendor A",
        )
        cls.vendor_b = Vendor.objects.create(
            owner=cls.other_vendor_user,
            name="Vendor B",
        )

        # VendorStaff.save() auto-creates "Main Branch", so
        # these are available after vendor creation.
        cls.branch_a = cls.vendor_a.branches.get(name="Main Branch")
        cls.branch_b = cls.vendor_b.branches.get(name="Main Branch")

        # ── STAFF MEMBERSHIPS ──────────────────────────────
        cls.owner_staff = VendorStaff.objects.create(
            vendor=cls.vendor_a,
            branch=cls.branch_a,
            user=cls.owner_user,
            role="owner",
        )
        cls.manager_staff = VendorStaff.objects.create(
            vendor=cls.vendor_a,
            branch=cls.branch_a,
            user=cls.manager_user,
            role="manager",
        )
        VendorStaff.objects.create(
            vendor=cls.vendor_b,
            branch=cls.branch_b,
            user=cls.other_vendor_user,
            role="owner",
        )

        # ── CATEGORIES & PRODUCTS ──────────────────────────
        cls.category_a = Category.objects.create(
            vendor=cls.vendor_a,
            name="Electronics",
        )
        cls.category_b = Category.objects.create(
            vendor=cls.vendor_b,
            name="Furniture",
        )

        cls.product_a = Product.objects.create(
            vendor=cls.vendor_a,
            category=cls.category_a,
            name="Widget",
            price=25.00,
        )
        cls.product_b = Product.objects.create(
            vendor=cls.vendor_a,
            category=cls.category_a,
            name="Gadget",
            price=50.00,
        )
        cls.product_c = Product.objects.create(
            vendor=cls.vendor_b,
            category=cls.category_b,
            name="Chair",
            price=100.00,
        )

        # ── INVENTORY ──────────────────────────────────────
        # Stock vendor A's branch with enough items
        cls.inv_widget = Inventory.objects.create(
            product=cls.product_a,
            branch=cls.branch_a,
            quantity=20,
        )
        cls.inv_gadget = Inventory.objects.create(
            product=cls.product_b,
            branch=cls.branch_a,
            quantity=10,
        )
        # Stock vendor B's branch
        cls.inv_chair = Inventory.objects.create(
            product=cls.product_c,
            branch=cls.branch_b,
            quantity=5,
        )

    # ── HELPERS ────────────────────────────────────────────

    def _client(self, user):
        """Return an APIClient pre-authenticated as *user*."""
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        return client

    def _order_create_payload(self, branch, product_id, quantity=5):
        return {
            "branch": branch.id,
            "customer_name": "John Doe",
            "customer_phone": "08012345678",
            "items": [
                {"product": product_id, "quantity": quantity},
            ],
        }

    @staticmethod
    def _create_sample_order(user, vendor, branch, product, quantity=5):
        """Create an order directly via the service (bypassing API)."""
        from apps.orders.services import create_order_with_items

        return create_order_with_items(
            vendor=vendor,
            branch=branch,
            created_by=user,
            customer_name="Jane Smith",
            customer_phone="08098765432",
            items_data=[{"product": product.id, "quantity": quantity}],
        )


# =====================================================================
#  ORDER CREATION
# =====================================================================


class OrderCreateTests(OrderTestCaseBase):
    @patch("apps.payments.services.create_payment_for_order")
    def test_owner_can_create_order(self, mock_payment):
        """Owner of a vendor can successfully create an order."""
        client = self._client(self.owner_user)
        payload = self._order_create_payload(self.branch_a, self.product_a.id, 5)

        response = client.post("/api/orders/create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["customer_name"], "John Doe")
        self.assertEqual(response.data["status"], "pending")

        # Verify inventory was deducted
        self.inv_widget.refresh_from_db()
        self.assertEqual(self.inv_widget.quantity, 15)  # 20 - 5

        # Verify order item was created
        order = Order.objects.get(id=response.data["id"])
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().quantity, 5)
        self.assertEqual(order.items.first().unit_price, 25.00)
        self.assertEqual(order.total_amount, 125.00)  # 5 × 25

    @patch("apps.payments.services.create_payment_for_order")
    def test_manager_can_create_order(self, mock_payment):
        """Manager role can also create orders."""
        client = self._client(self.manager_user)
        payload = self._order_create_payload(self.branch_a, self.product_a.id, 3)

        response = client.post("/api/orders/create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unauthenticated_user_cannot_create_order(self):
        """POST without auth returns 401."""
        client = APIClient()
        payload = self._order_create_payload(self.branch_a, self.product_a.id, 1)
        response = client.post("/api/orders/create/", payload, format="json")
        # DRF returns 401 for unauthenticated with IsAuthenticated permission
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_create_order_insufficient_stock(self):
        """Order with quantity > available stock is rejected."""
        client = self._client(self.owner_user)
        # Only 10 gadgets in stock — request 15
        payload = self._order_create_payload(self.branch_a, self.product_b.id, 15)

        response = client.post("/api/orders/create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Insufficient stock", str(response.data))

    def test_unaffiliated_user_cannot_create_order(self):
        """User without any vendor staff membership gets a 400 validation error."""
        client = self._client(self.unaffiliated_user)
        payload = self._order_create_payload(self.branch_a, self.product_a.id, 1)

        response = client.post("/api/orders/create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not assigned to any vendor", str(response.data).lower())

    def test_cannot_create_order_for_other_vendors_branch(self):
        """Branch from a different vendor is rejected."""
        client = self._client(self.owner_user)
        # Try to order using vendor B's branch
        payload = self._order_create_payload(self.branch_b, self.product_a.id, 1)

        response = client.post("/api/orders/create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Branch does not belong", str(response.data))

    @patch("apps.payments.services.create_payment_for_order")
    def test_create_order_with_multiple_items(self, mock_payment):
        """Orders with multiple line items calculate total correctly."""
        client = self._client(self.owner_user)
        payload = {
            "branch": self.branch_a.id,
            "customer_name": "Multi Item",
            "customer_phone": "08011111111",
            "items": [
                {"product": self.product_a.id, "quantity": 2},  # 2 × 25 = 50
                {"product": self.product_b.id, "quantity": 3},  # 3 × 50 = 150
            ],
        }

        response = client.post("/api/orders/create/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(id=response.data["id"])
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.total_amount, 200.00)  # 50 + 150


# =====================================================================
#  ORDER LISTING & DETAIL
# =====================================================================


class OrderListDetailTests(OrderTestCaseBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        # Create sample orders for both vendors
        cls.order_a1 = cls._create_sample_order(
            cls.owner_user, cls.vendor_a, cls.branch_a, cls.product_a, 2
        )
        cls.order_a2 = cls._create_sample_order(
            cls.owner_user, cls.vendor_a, cls.branch_a, cls.product_b, 1
        )
        cls.order_b1 = cls._create_sample_order(
            cls.other_vendor_user, cls.vendor_b, cls.branch_b, cls.product_c, 3
        )

    def test_list_own_orders(self):
        """User sees only orders belonging to their vendor."""
        client = self._client(self.owner_user)
        response = client.get("/api/orders/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in response.data]
        self.assertIn(self.order_a1.id, ids)
        self.assertIn(self.order_a2.id, ids)
        self.assertNotIn(self.order_b1.id, ids)  # multi-tenant isolation

    def test_other_vendor_orders_not_visible(self):
        """Vendor B user cannot see Vendor A orders."""
        client = self._client(self.other_vendor_user)
        response = client.get("/api/orders/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in response.data]
        self.assertIn(self.order_b1.id, ids)
        self.assertNotIn(self.order_a1.id, ids)

    def test_order_detail_own_order(self):
        """User can retrieve their own order's detail."""
        client = self._client(self.owner_user)
        response = client.get(f"/api/orders/{self.order_a1.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.order_a1.id)
        self.assertEqual(response.data["customer_name"], "Jane Smith")

    def test_order_detail_cross_vendor_blocked(self):
        """User cannot access another vendor's order."""
        client = self._client(self.other_vendor_user)
        response = client.get(f"/api/orders/{self.order_a1.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =====================================================================
#  ORDER STATUS TRANSITIONS
# =====================================================================


class OrderStatusTransitionTests(OrderTestCaseBase):
    def setUp(self):
        super().setUp()
        # Fresh order for each test so state is predictable
        self._create_fresh_order()

    def _create_fresh_order(self):
        from apps.orders.services import create_order_with_items

        self.order = create_order_with_items(
            vendor=self.vendor_a,
            branch=self.branch_a,
            created_by=self.owner_user,
            customer_name="Transition Test",
            customer_phone="08000000000",
            items_data=[{"product": self.product_a.id, "quantity": 2}],
        )
        self.assertEqual(self.order.status, "pending")

    @patch("apps.orders.views.send_notification_task.delay")
    @patch("apps.orders.views.create_delivery_from_order")
    def test_valid_transition_pending_to_confirmed(
        self, mock_delivery, mock_notification
    ):
        """pending → confirmed is a valid transition."""
        client = self._client(self.owner_user)
        response = client.post(
            f"/api/orders/{self.order.id}/status/",
            {"status": "confirmed"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "confirmed")

        # Status log should be created
        self.assertTrue(
            OrderStatusLog.objects.filter(
                order=self.order,
                previous_status="pending",
                new_status="confirmed",
            ).exists()
        )

        # Delivery creation should be triggered
        mock_delivery.assert_called_once_with(self.order)

    @patch("apps.orders.views.send_notification_task.delay")
    @patch("apps.orders.views.create_delivery_from_order")
    def test_valid_transition_confirmed_to_completed(
        self, mock_delivery, mock_notification
    ):
        """confirmed → completed is a valid transition."""
        # First transition to confirmed
        self.order.status = "confirmed"
        self.order.save()

        client = self._client(self.owner_user)
        response = client.post(
            f"/api/orders/{self.order.id}/status/",
            {"status": "completed"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "completed")

    @patch("apps.orders.views.send_notification_task.delay")
    def test_invalid_transition_returns_400(self, mock_notification):
        """pending → completed (skipping confirmed) is rejected."""
        client = self._client(self.owner_user)
        response = client.post(
            f"/api/orders/{self.order.id}/status/",
            {"status": "completed"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot change status", str(response.data))

    @patch("apps.orders.views.send_notification_task.delay")
    def test_transition_by_other_vendor_blocked(self, mock_notification):
        """User from Vendor B cannot update Vendor A's order."""
        client = self._client(self.other_vendor_user)
        response = client.post(
            f"/api/orders/{self.order.id}/status/",
            {"status": "confirmed"},
            format="json",
        )

        # validate_vendor_access raises PermissionDenied (403)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("apps.orders.views.send_notification_task.delay")
    def test_transition_unauthenticated(self, mock_notification):
        """Unauthenticated request returns 401."""
        client = APIClient()
        response = client.post(
            f"/api/orders/{self.order.id}/status/",
            {"status": "confirmed"},
            format="json",
        )

        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    @patch("apps.orders.views.send_notification_task.delay")
    def test_invalid_status_value_returns_400(self, mock_notification):
        """Sending an invalid status choice returns 400."""
        client = self._client(self.owner_user)
        response = client.post(
            f"/api/orders/{self.order.id}/status/",
            {"status": "nonexistent"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("apps.orders.views.send_notification_task.delay")
    def test_cancel_pending_order_restores_inventory(self, mock_notification):
        """Cancelling a pending order restores the deducted stock."""
        # setUp deducted 2 from product_a's inventory (started at 20)
        self.inv_widget.refresh_from_db()
        self.assertEqual(self.inv_widget.quantity, 18)

        client = self._client(self.owner_user)
        response = client.post(
            f"/api/orders/{self.order.id}/status/",
            {"status": "cancelled"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")

        # Inventory should be restored: 18 + 2 = 20
        inv = Inventory.objects.get(product=self.product_a, branch=self.branch_a)
        self.assertEqual(inv.quantity, 20)


# =====================================================================
#  MULTI-TENANT ISOLATION
# =====================================================================


class MultiTenantIsolationTests(OrderTestCaseBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Create orders for both vendors
        cls.order_a = cls._create_sample_order(
            cls.owner_user, cls.vendor_a, cls.branch_a, cls.product_a, 1
        )
        cls.order_b = cls._create_sample_order(
            cls.other_vendor_user, cls.vendor_b, cls.branch_b, cls.product_c, 1
        )

    def test_vendor_a_cannot_see_vendor_b_orders(self):
        """Full isolation: user can only interact with their own vendor's data."""
        client = self._client(self.owner_user)
        response = client.get("/api/orders/")
        order_ids = [o["id"] for o in response.data]
        self.assertIn(self.order_a.id, order_ids)
        self.assertNotIn(self.order_b.id, order_ids)

        # Detail also blocked (scoped queryset returns 404)
        response = client.get(f"/api/orders/{self.order_b.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Status update also blocked (validate_vendor_access returns 403)
        response = client.post(
            f"/api/orders/{self.order_b.id}/status/",
            {"status": "confirmed"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_b_cannot_see_vendor_a_orders(self):
        """Mirror isolation check for the other vendor."""
        client = self._client(self.other_vendor_user)
        response = client.get("/api/orders/")
        order_ids = [o["id"] for o in response.data]
        self.assertIn(self.order_b.id, order_ids)
        self.assertNotIn(self.order_a.id, order_ids)

        response = client.get(f"/api/orders/{self.order_a.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_order_counts_are_vendor_scoped(self):
        """Each vendor sees exactly their own order count."""
        client_a = self._client(self.owner_user)
        client_b = self._client(self.other_vendor_user)

        resp_a = client_a.get("/api/orders/")
        resp_b = client_b.get("/api/orders/")

        self.assertEqual(len(resp_a.data), 1)
        self.assertEqual(len(resp_b.data), 1)
