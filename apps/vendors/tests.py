from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.vendors.models import (
    Branch,
    Vendor,
    VendorInvitation,
    VendorSettings,
    VendorStaff,
)

User = get_user_model()


class VendorTestCaseBase(APITestCase):
    """Shared fixtures for all vendor tests."""

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
        cls.inventory_staff = User.objects.create_user(
            email="inventory@test.com",
            username="inventory_a",
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

        # VendorStaff.save() auto-creates "Main Branch"
        cls.branch_a = cls.vendor_a.branches.get(name="Main Branch")
        cls.branch_b = cls.vendor_b.branches.get(name="Main Branch")

        # ── STAFF MEMBERSHIPS ──────────────────────────────
        cls.owner_a_staff = VendorStaff.objects.create(
            vendor=cls.vendor_a,
            branch=cls.branch_a,
            user=cls.owner_a,
            role="owner",
        )
        cls.manager_a_staff = VendorStaff.objects.create(
            vendor=cls.vendor_a,
            branch=cls.branch_a,
            user=cls.manager_a,
            role="manager",
        )
        cls.inventory_a_staff = VendorStaff.objects.create(
            vendor=cls.vendor_a,
            branch=cls.branch_a,
            user=cls.inventory_staff,
            role="inventory",
        )
        VendorStaff.objects.create(
            vendor=cls.vendor_b,
            branch=cls.branch_b,
            user=cls.owner_b,
            role="owner",
        )

        # ── ADDITIONAL BRANCHES ────────────────────────────
        cls.branch_a_2 = Branch.objects.create(
            vendor=cls.vendor_a,
            name="Branch 2",
            address="456 Side St",
        )

    # ── HELPERS ────────────────────────────────────────────

    def _client(self, user):
        client = APIClient()
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        return client


# =====================================================================
#  VENDOR CRUD
# =====================================================================


class VendorCRUDTests(VendorTestCaseBase):

    def test_create_vendor_success(self):
        """Authenticated user can create a vendor and becomes owner."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/vendors/create/",
            {"name": "New Vendor", "description": "A new vendor"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "New Vendor")

        # Owner staff membership and Main Branch auto-created
        vendor = Vendor.objects.get(id=response.data["id"])
        self.assertEqual(vendor.owner, self.owner_a)
        self.assertTrue(vendor.branches.filter(name="Main Branch").exists())
        self.assertTrue(
            VendorStaff.objects.filter(
                vendor=vendor, user=self.owner_a, role="owner"
            ).exists()
        )

    def test_create_vendor_unauthenticated(self):
        """Unauthenticated request returns 401."""
        client = APIClient()
        response = client.post(
            "/api/vendors/create/",
            {"name": "Ghost Vendor"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_own_vendors(self):
        """User sees vendors they own or are staff on."""
        client = self._client(self.owner_a)
        response = client.get("/api/vendors/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [v["id"] for v in response.data]
        self.assertIn(self.vendor_a.id, ids)
        self.assertNotIn(self.vendor_b.id, ids)

    def test_list_vendors_as_staff(self):
        """Staff member can see their assigned vendor."""
        client = self._client(self.manager_a)
        response = client.get("/api/vendors/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [v["id"] for v in response.data]
        self.assertIn(self.vendor_a.id, ids)

    def test_list_vendors_other_vendor_isolation(self):
        """Vendor B user cannot see Vendor A."""
        client = self._client(self.owner_b)
        response = client.get("/api/vendors/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [v["id"] for v in response.data]
        self.assertIn(self.vendor_b.id, ids)
        self.assertNotIn(self.vendor_a.id, ids)


# =====================================================================
#  STAFF MANAGEMENT
# =====================================================================


class StaffManagementTests(VendorTestCaseBase):

    def test_owner_can_create_staff(self):
        """Owner role can add staff to their vendor."""
        new_user = User.objects.create_user(
            email="newstaff@test.com",
            username="newstaff",
            password="testpass123",
        )
        client = self._client(self.owner_a)
        response = client.post(
            "/api/vendors/staff/create/",
            {
                "vendor": self.vendor_a.id,
                "user": new_user.id,
                "role": "manager",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["role"], "manager")

        # Staff membership created
        self.assertTrue(
            VendorStaff.objects.filter(vendor=self.vendor_a, user=new_user).exists()
        )

    def test_non_owner_cannot_create_staff(self):
        """Manager role cannot add staff (only owner)."""
        new_user = User.objects.create_user(
            email="newstaff2@test.com",
            username="newstaff2",
            password="testpass123",
        )
        client = self._client(self.manager_a)
        response = client.post(
            "/api/vendors/staff/create/",
            {
                "vendor": self.vendor_a.id,
                "user": new_user.id,
                "role": "manager",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_staff_cross_vendor_blocked(self):
        """User from Vendor B cannot add staff to Vendor A."""
        new_user = User.objects.create_user(
            email="newstaff3@test.com",
            username="newstaff3",
            password="testpass123",
        )
        client = self._client(self.owner_b)
        response = client.post(
            "/api/vendors/staff/create/",
            {
                "vendor": self.vendor_a.id,
                "user": new_user.id,
                "role": "manager",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_staff_blocked(self):
        """Adding an already-existing staff member is rejected."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/vendors/staff/create/",
            {
                "vendor": self.vendor_a.id,
                "user": self.manager_a.id,
                "role": "manager",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already belongs", str(response.data).lower())

    def test_list_staff_own_vendor(self):
        """Owner can list staff for their vendor."""
        client = self._client(self.owner_a)
        response = client.get(f"/api/vendors/staff/?vendor_id={self.vendor_a.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user_ids = [s["user"] for s in response.data]

        # user field is the user ID in VendorStaffSerializer
        self.assertIn(self.owner_a.id, user_ids)

    def test_list_staff_without_vendor_id(self):
        """Missing vendor_id returns empty list."""
        client = self._client(self.owner_a)
        response = client.get("/api/vendors/staff/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_list_staff_cross_vendor_blocked(self):
        """Cannot list staff of another vendor."""
        client = self._client(self.owner_b)
        response = client.get(f"/api/vendors/staff/?vendor_id={self.vendor_a.id}")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# =====================================================================
#  BRANCH MANAGEMENT
# =====================================================================


class BranchManagementTests(VendorTestCaseBase):

    def test_owner_can_create_branch(self):
        """Owner can create a branch for their vendor."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/vendors/branches/create/",
            {
                "vendor": self.vendor_a.id,
                "name": "New Branch",
                "address": "123 Main St",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "New Branch")

    def test_manager_can_create_branch(self):
        """Manager can also create branches."""
        client = self._client(self.manager_a)
        response = client.post(
            "/api/vendors/branches/create/",
            {
                "vendor": self.vendor_a.id,
                "name": "Manager Branch",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_inventory_staff_cannot_create_branch(self):
        """Inventory staff cannot create branches."""
        client = self._client(self.inventory_staff)
        response = client.post(
            "/api/vendors/branches/create/",
            {
                "vendor": self.vendor_a.id,
                "name": "Staff Branch",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_branch_name_blocked(self):
        """Duplicate branch name per vendor is rejected."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/vendors/branches/create/",
            {
                "vendor": self.vendor_a.id,
                "name": "Main Branch",  # Already exists
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already exists", str(response.data))

    def test_list_branches_own_vendor(self):
        """User can list branches for their vendor."""
        client = self._client(self.owner_a)
        response = client.get(f"/api/vendors/branches/?vendor_id={self.vendor_a.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [b["name"] for b in response.data]
        self.assertIn("Main Branch", names)
        self.assertIn("Branch 2", names)

    def test_list_branches_without_vendor_id(self):
        """Missing vendor_id returns empty list."""
        client = self._client(self.owner_a)
        response = client.get("/api/vendors/branches/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_list_branches_cross_vendor_blocked(self):
        """Cannot list branches of another vendor."""
        client = self._client(self.owner_b)
        response = client.get(f"/api/vendors/branches/?vendor_id={self.vendor_a.id}")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# =====================================================================
#  VENDOR SETTINGS
# =====================================================================


class VendorSettingsTests(VendorTestCaseBase):

    def test_get_settings(self):
        """Owner can retrieve vendor settings."""
        # Ensure settings exist
        VendorSettings.objects.get_or_create(vendor=self.vendor_a)

        client = self._client(self.owner_a)
        response = client.get(f"/api/vendors/{self.vendor_a.id}/settings/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("currency", response.data)
        self.assertIn("enable_email_notifications", response.data)

    def test_update_settings(self):
        """Owner can update vendor settings."""
        VendorSettings.objects.get_or_create(vendor=self.vendor_a)

        client = self._client(self.owner_a)
        response = client.patch(
            f"/api/vendors/{self.vendor_a.id}/settings/",
            {"currency": "USD", "auto_process_payments": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["currency"], "USD")
        self.assertTrue(response.data["auto_process_payments"])

    def test_settings_cross_vendor_blocked(self):
        """Cannot access another vendor's settings."""
        client = self._client(self.owner_b)
        response = client.get(f"/api/vendors/{self.vendor_a.id}/settings/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# =====================================================================
#  INVITATIONS
# =====================================================================


class InvitationTests(VendorTestCaseBase):

    @patch("apps.vendors.views.send_invitation_email")
    def test_create_invitation(self, mock_send):
        """Owner can create an invitation for a new staff member."""
        client = self._client(self.owner_a)
        response = client.post(
            "/api/vendors/invitations/create/",
            {
                "vendor": self.vendor_a.id,
                "email": "invitee@test.com",
                "role": "manager",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["email"], "invitee@test.com")
        mock_send.assert_called_once()

    @patch("apps.vendors.views.send_invitation_email")
    def test_manager_can_create_invitation(self, mock_send):
        """Manager can also create invitations."""
        client = self._client(self.manager_a)
        response = client.post(
            "/api/vendors/invitations/create/",
            {
                "vendor": self.vendor_a.id,
                "email": "invitee2@test.com",
                "role": "dispatcher",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "pending")

    @patch("apps.vendors.views.send_invitation_email")
    def test_inventory_staff_cannot_create_invitation(self, mock_send):
        """Inventory staff cannot create invitations."""
        client = self._client(self.inventory_staff)
        response = client.post(
            "/api/vendors/invitations/create/",
            {
                "vendor": self.vendor_a.id,
                "email": "invitee3@test.com",
                "role": "manager",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_invitation_duplicate_active_blocked(self):
        """Creating a duplicate active invitation is blocked."""
        # Create first invitation
        from datetime import timedelta

        from django.utils import timezone
        from django.utils.crypto import get_random_string

        VendorInvitation.objects.create(
            vendor=self.vendor_a,
            email="dup@test.com",
            role="manager",
            invitation_token=get_random_string(64),
            created_by=self.owner_a,
            expires_at=timezone.now() + timedelta(days=7),
        )

        client = self._client(self.owner_a)
        response = client.post(
            "/api/vendors/invitations/create/",
            {
                "vendor": self.vendor_a.id,
                "email": "dup@test.com",
                "role": "manager",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already exists", str(response.data).lower())

    def test_accept_invitation(self):
        """Accepting a valid invitation creates staff membership."""
        from datetime import timedelta

        from django.utils import timezone

        token = "accept-test-token-789"
        VendorInvitation.objects.create(
            vendor=self.vendor_a,
            email="accept@test.com",
            role="rider",
            invitation_token=token,
            created_by=self.owner_a,
            expires_at=timezone.now() + timedelta(days=7),
        )

        client = APIClient()
        response = client.post(
            "/api/vendors/invitations/accept/",
            {"token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("accepted successfully", response.data["message"])

        # Staff membership created
        accepted_user = User.objects.get(email="accept@test.com")
        self.assertTrue(
            VendorStaff.objects.filter(
                vendor=self.vendor_a, user=accepted_user
            ).exists()
        )

    def test_accept_invitation_invalid_token(self):
        """Invalid token returns 400."""
        client = APIClient()
        response = client.post(
            "/api/vendors/invitations/accept/",
            {"token": "nonexistent-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid", str(response.data))

    def test_reject_invitation(self):
        """Rejecting a pending invitation updates its status."""
        from datetime import timedelta

        from django.utils import timezone

        token = "reject-test-token-abc"
        inv = VendorInvitation.objects.create(
            vendor=self.vendor_a,
            email="reject@test.com",
            role="manager",
            invitation_token=token,
            created_by=self.owner_a,
            expires_at=timezone.now() + timedelta(days=7),
        )

        client = APIClient()
        response = client.post(
            "/api/vendors/invitations/reject/",
            {"token": token},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("rejected", response.data["message"])

        inv.refresh_from_db()
        self.assertEqual(inv.status, "rejected")

    @patch("apps.vendors.views.resend_invitation")
    def test_resend_invitation(self, mock_resend):
        """Owner can resend a pending invitation."""
        from datetime import timedelta

        from django.utils import timezone
        from django.utils.crypto import get_random_string

        inv = VendorInvitation.objects.create(
            vendor=self.vendor_a,
            email="resend@test.com",
            role="manager",
            invitation_token=get_random_string(64),
            created_by=self.owner_a,
            expires_at=timezone.now() + timedelta(days=7),
        )
        mock_resend.return_value = True

        client = self._client(self.owner_a)
        response = client.post(
            f"/api/vendors/invitations/{inv.id}/resend/",
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("resent", response.data["message"])

    def test_list_invitations(self):
        """Owner can list invitations for their vendor."""
        from datetime import timedelta

        from django.utils import timezone
        from django.utils.crypto import get_random_string

        VendorInvitation.objects.create(
            vendor=self.vendor_a,
            email="list1@test.com",
            role="manager",
            invitation_token=get_random_string(64),
            created_by=self.owner_a,
            expires_at=timezone.now() + timedelta(days=7),
        )
        VendorInvitation.objects.create(
            vendor=self.vendor_a,
            email="list2@test.com",
            role="rider",
            invitation_token=get_random_string(64),
            created_by=self.owner_a,
            expires_at=timezone.now() + timedelta(days=7),
        )

        client = self._client(self.owner_a)
        response = client.get(f"/api/vendors/invitations/?vendor_id={self.vendor_a.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = [i["email"] for i in response.data]
        self.assertIn("list1@test.com", emails)
        self.assertIn("list2@test.com", emails)

    def test_list_invitations_cross_vendor_blocked(self):
        """Cannot list invitations of another vendor."""
        client = self._client(self.owner_b)
        response = client.get(f"/api/vendors/invitations/?vendor_id={self.vendor_a.id}")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
