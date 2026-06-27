from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.inventory.models import Category, Inventory, InventoryLog, Product
from apps.vendors.models import Vendor, VendorStaff

User = get_user_model()


class InventoryTestCaseBase(APITestCase):
    """Shared fixtures for all inventory tests."""

    @classmethod
    def setUpTestData(cls):

        # ── USERS ──────────────────────────────────────────
        cls.owner_a = User.objects.create_user(
            email="owner_a@test.com",
            username="owner_a",
            password="testpass123",
            role="vendor",
        )
        cls.manager_a = User.objects.create_user(
            email="manager_a@test.com",
            username="manager_a",
            password="testpass123",
            role="vendor",
        )
        cls.inventory_user = User.objects.create_user(
            email="inv_staff@test.com",
            username="inv_staff",
            password="testpass123",
            role="vendor",
        )
        cls.owner_b = User.objects.create_user(
            email="owner_b@test.com",
            username="owner_b",
            password="testpass123",
            role="vendor",
        )
        cls.stranger = User.objects.create_user(
            email="stranger@test.com",
            username="stranger",
            password="testpass123",
            role="staff",
        )

        # ── VENDORS ────────────────────────────────────────
        cls.vendor_a = Vendor.objects.create(owner=cls.owner_a, name="Vendor A")
        cls.vendor_b = Vendor.objects.create(owner=cls.owner_b, name="Vendor B")

        cls.branch_a = cls.vendor_a.branches.get(name="Main Branch")
        cls.branch_b = cls.vendor_b.branches.get(name="Main Branch")

        # ── STAFF ──────────────────────────────────────────
        VendorStaff.objects.create(
            vendor=cls.vendor_a,
            branch=cls.branch_a,
            user=cls.owner_a,
            role="owner",
        )
        VendorStaff.objects.create(
            vendor=cls.vendor_a,
            branch=cls.branch_a,
            user=cls.manager_a,
            role="manager",
        )
        VendorStaff.objects.create(
            vendor=cls.vendor_a,
            branch=cls.branch_a,
            user=cls.inventory_user,
            role="inventory",
        )
        VendorStaff.objects.create(
            vendor=cls.vendor_b,
            branch=cls.branch_b,
            user=cls.owner_b,
            role="owner",
        )

        # ── CATEGORIES ─────────────────────────────────────
        cls.category_a = Category.objects.create(
            vendor=cls.vendor_a,
            name="Electronics",
        )
        cls.category_b = Category.objects.create(
            vendor=cls.vendor_b,
            name="Furniture",
        )

        # ── PRODUCTS ───────────────────────────────────────
        cls.product_a = Product.objects.create(
            vendor=cls.vendor_a,
            category=cls.category_a,
            name="Widget",
            price=25.00,
        )
        cls.product_b = Product.objects.create(
            vendor=cls.vendor_b,
            category=cls.category_b,
            name="Chair",
            price=100.00,
        )

        # ── INVENTORY ──────────────────────────────────────
        cls.inv_a = Inventory.objects.create(
            product=cls.product_a,
            branch=cls.branch_a,
            quantity=50,
            low_stock_threshold=5,
        )
        cls.inv_b = Inventory.objects.create(
            product=cls.product_b,
            branch=cls.branch_b,
            quantity=10,
            low_stock_threshold=3,
        )

    # ── HELPERS ────────────────────────────────────────────

    def _client(self, user):
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        return client


# =====================================================================
#  CATEGORIES
# =====================================================================


class CategoryTests(InventoryTestCaseBase):

    def test_owner_can_create_category(self):
        """Owner can create a category for their vendor."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/inventory/categories/create/",
            {"vendor": self.vendor_a.id, "name": "Groceries"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Groceries")
        self.assertTrue(
            Category.objects.filter(vendor=self.vendor_a, name="Groceries").exists()
        )

    def test_manager_can_create_category(self):
        """Manager can also create categories."""
        client = self._client(self.manager_a)
        response = client.post(
            "/api/inventory/categories/create/",
            {"vendor": self.vendor_a.id, "name": "Beverages"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_inventory_staff_cannot_create_category(self):
        """Inventory staff role cannot create categories."""
        client = self._client(self.inventory_user)
        response = client.post(
            "/api/inventory/categories/create/",
            {"vendor": self.vendor_a.id, "name": "Snacks"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_category_name_per_vendor_blocked(self):
        """Duplicate category name within same vendor is rejected."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/inventory/categories/create/",
            {"vendor": self.vendor_a.id, "name": "Electronics"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already exists", str(response.data))

    def test_create_category_cross_vendor_blocked(self):
        """User from Vendor B cannot create category under Vendor A."""
        client = self._client(self.owner_b)
        response = client.post(
            "/api/inventory/categories/create/",
            {"vendor": self.vendor_a.id, "name": "Tools"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create_category(self):
        """Unauthenticated request returns 401."""
        client = APIClient()
        response = client.post(
            "/api/inventory/categories/create/",
            {"vendor": self.vendor_a.id, "name": "Test"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# =====================================================================
#  PRODUCTS
# =====================================================================


class ProductTests(InventoryTestCaseBase):

    def test_create_product_with_category(self):
        """Owner can create a product with a category."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/inventory/products/create/",
            {
                "vendor": self.vendor_a.id,
                "category": self.category_a.id,
                "name": "Smartphone",
                "price": 500.00,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Smartphone")
        self.assertEqual(response.data["category"], self.category_a.id)
        self.assertTrue(response.data["sku"].startswith("PRD-"))

        # Inventory should be initialized for all branches
        product = Product.objects.get(id=response.data["id"])
        self.assertEqual(
            product.inventory_records.count(),
            self.vendor_a.branches.count(),
        )

    def test_create_product_auto_generates_sku(self):
        """Product without SKU gets auto-generated."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/inventory/products/create/",
            {
                "vendor": self.vendor_a.id,
                "name": "Tablet",
                "price": 300.00,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("sku", response.data)
        self.assertTrue(len(response.data["sku"]) > 0)

    def test_create_product_category_mismatch_blocked(self):
        """Product category must belong to the same vendor."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/inventory/products/create/",
            {
                "vendor": self.vendor_a.id,
                "category": self.category_b.id,  # Vendor B's category
                "name": "Illegal Product",
                "price": 10.00,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("does not belong", str(response.data).lower())

    def test_create_product_cross_vendor_blocked(self):
        """User from Vendor B cannot create product under Vendor A."""
        client = self._client(self.owner_b)
        response = client.post(
            "/api/inventory/products/create/",
            {
                "vendor": self.vendor_a.id,
                "name": "Stolen Product",
                "price": 99.00,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_create_product(self):
        """Manager can also create products."""
        client = self._client(self.manager_a)
        response = client.post(
            "/api/inventory/products/create/",
            {
                "vendor": self.vendor_a.id,
                "name": "Laptop",
                "price": 1200.00,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_inventory_staff_cannot_create_product(self):
        """Inventory staff cannot create products."""
        client = self._client(self.inventory_user)
        response = client.post(
            "/api/inventory/products/create/",
            {
                "vendor": self.vendor_a.id,
                "name": "Headphones",
                "price": 50.00,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# =====================================================================
#  INVENTORY ADJUSTMENTS
# =====================================================================


class InventoryAdjustmentTests(InventoryTestCaseBase):

    def test_stock_in_increases_quantity(self):
        """Stock In adjustment increases inventory quantity."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/inventory/inventory/adjust/",
            {
                "inventory_id": self.inv_a.id,
                "change_quantity": 10,
                "adjustment_type": "stock_in",
                "reason": "New shipment arrived",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_quantity"], 60)  # 50 + 10
        self.assertFalse(response.data["is_low_stock"])

        # InventoryLog should be created
        self.assertTrue(
            InventoryLog.objects.filter(
                inventory=self.inv_a,
                adjustment_type="stock_in",
                change_quantity=10,
            ).exists()
        )

    def test_stock_out_decreases_quantity(self):
        """Stock Out adjustment decreases inventory quantity."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/inventory/inventory/adjust/",
            {
                "inventory_id": self.inv_a.id,
                "change_quantity": 5,
                "adjustment_type": "stock_out",
                "reason": "Order fulfillment",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_quantity"], 45)  # 50 - 5

    def test_stock_out_insufficient_stock_blocked(self):
        """Stock Out exceeding available quantity is rejected."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/inventory/inventory/adjust/",
            {
                "inventory_id": self.inv_a.id,
                "change_quantity": 999,
                "adjustment_type": "stock_out",
                "reason": "Way too many",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Insufficient stock", str(response.data))

    def test_adjustment_sets_exact_quantity(self):
        """Adjustment type sets quantity directly."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/inventory/inventory/adjust/",
            {
                "inventory_id": self.inv_a.id,
                "change_quantity": 100,
                "adjustment_type": "adjustment",
                "reason": "Stock count correction",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_quantity"], 100)  # Set directly to 100

    def test_inventory_staff_can_adjust(self):
        """Inventory staff role can make adjustments."""
        client = self._client(self.inventory_user)
        response = client.post(
            "/api/inventory/inventory/adjust/",
            {
                "inventory_id": self.inv_a.id,
                "change_quantity": 10,
                "adjustment_type": "stock_in",
                "reason": "Restock",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_stranger_cannot_adjust(self):
        """User not associated with the vendor cannot adjust."""
        client = self._client(self.stranger)
        response = client.post(
            "/api/inventory/inventory/adjust/",
            {
                "inventory_id": self.inv_a.id,
                "change_quantity": 10,
                "adjustment_type": "stock_in",
                "reason": "Hack attempt",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_adjust_cross_vendor_blocked(self):
        """User from Vendor B cannot adjust Vendor A's inventory."""
        client = self._client(self.owner_b)
        response = client.post(
            "/api/inventory/inventory/adjust/",
            {
                "inventory_id": self.inv_a.id,
                "change_quantity": 1,
                "adjustment_type": "stock_in",
                "reason": "Cross-vendor attempt",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_adjust_nonexistent_inventory(self):
        """Adjusting a non-existent inventory record returns 400."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/inventory/inventory/adjust/",
            {
                "inventory_id": 99999,
                "change_quantity": 10,
                "adjustment_type": "stock_in",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not found", str(response.data).lower())


# =====================================================================
#  LOW STOCK TRIGGER
# =====================================================================


class LowStockTests(InventoryTestCaseBase):

    @patch("apps.notifications.tasks.send_notification_task.delay")
    def test_low_stock_trigger_on_stock_out(self, mock_notify):
        """Stocking out below threshold triggers low stock alert."""
        client = self._client(self.owner_a)
        # Stock out 48 units from 50 → 2 remaining (threshold is 5)
        response = client.post(
            "/api/inventory/inventory/adjust/",
            {
                "inventory_id": self.inv_a.id,
                "change_quantity": 48,
                "adjustment_type": "stock_out",
                "reason": "Bulk order",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_low_stock"])
        self.assertEqual(response.data["new_quantity"], 2)

        # Low stock notification should be queued
        mock_notify.assert_called_once()
        call_args = mock_notify.call_args
        self.assertEqual(call_args[1]["notification_type"], "inventory")
        self.assertIn("Low Stock", call_args[1]["title"])

    def test_above_threshold_not_low_stock(self):
        """Stock above threshold does not flag as low stock."""
        self.inv_a.low_stock_threshold = 5
        self.inv_a.quantity = 10
        self.inv_a.save()

        self.assertFalse(self.inv_a.is_low_stock())

    def test_at_threshold_is_low_stock(self):
        """Stock equal to threshold is considered low stock."""
        self.inv_a.quantity = 5
        self.inv_a.save()

        self.assertTrue(self.inv_a.is_low_stock())

    def test_below_threshold_is_low_stock(self):
        """Stock below threshold is considered low stock."""
        self.inv_a.quantity = 3
        self.inv_a.save()

        self.assertTrue(self.inv_a.is_low_stock())


# =====================================================================
#  INVENTORY LISTING
# =====================================================================


class InventoryListTests(InventoryTestCaseBase):

    def test_list_inventory_own_vendor(self):
        """User sees only inventory records for their vendor."""
        client = self._client(self.owner_a)
        response = client.get("/api/inventory/inventory/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [i["id"] for i in response.data]
        self.assertIn(self.inv_a.id, ids)
        self.assertNotIn(self.inv_b.id, ids)

    def test_list_inventory_filter_by_branch(self):
        """Filter inventory by branch ID."""
        client = self._client(self.owner_a)
        response = client.get(f"/api/inventory/inventory/?branch={self.branch_a.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [i["id"] for i in response.data]
        self.assertIn(self.inv_a.id, ids)

    def test_list_inventory_filter_by_product(self):
        """Filter inventory by product ID."""
        client = self._client(self.owner_a)
        response = client.get(f"/api/inventory/inventory/?product={self.product_a.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.inv_a.id)

    def test_list_inventory_unauthenticated(self):
        """Unauthenticated request returns 401."""
        client = APIClient()
        response = client.get("/api/inventory/inventory/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_inventory_cross_vendor_isolation(self):
        """Vendor B user cannot see Vendor A inventory."""
        client = self._client(self.owner_b)
        response = client.get("/api/inventory/inventory/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [i["id"] for i in response.data]
        self.assertIn(self.inv_b.id, ids)
        self.assertNotIn(self.inv_a.id, ids)
