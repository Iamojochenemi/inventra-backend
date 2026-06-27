from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class AuthTestCaseBase(APITestCase):
    """Shared fixtures for all auth tests."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="user@test.com",
            username="testuser",
            password="securepass123",
            role="vendor",
        )

    def _client(self, user=None):
        client = APIClient()
        if user:
            refresh = RefreshToken.for_user(user)
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        return client

    def _register_payload(self, overrides=None):
        payload = {
            "email": "newuser@test.com",
            "username": "newuser",
            "password": "NewPass123!",
            "role": "vendor",
            "phone_number": "08012345678",
        }
        if overrides:
            payload.update(overrides)
        return payload


# =====================================================================
#  REGISTRATION
# =====================================================================


class RegistrationTests(AuthTestCaseBase):

    @patch("apps.accounts.services.auth_service.send_verification_email")
    def test_register_success(self, mock_send):
        """Register a new user returns 201 with user data."""
        client = APIClient()
        payload = self._register_payload()
        response = client.post("/api/accounts/register/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["email"], "newuser@test.com")
        self.assertEqual(response.data["username"], "newuser")
        self.assertNotIn("password", response.data)

        # Verify user was created in DB
        self.assertTrue(User.objects.filter(email="newuser@test.com").exists())

        # Verification email should be triggered
        mock_send.assert_called_once()

    def test_register_duplicate_email(self):
        """Registering with an existing email returns 400."""
        client = APIClient()
        payload = self._register_payload({"email": "user@test.com"})
        response = client.post("/api/accounts/register/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_email(self):
        """Registering without email returns 400."""
        client = APIClient()
        payload = self._register_payload({"email": ""})
        response = client.post("/api/accounts/register/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_password(self):
        """Registering without password returns 400."""
        client = APIClient()
        payload = self._register_payload({"password": ""})
        response = client.post("/api/accounts/register/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_weak_password(self):
        """Registering with a weak password returns 400."""
        client = APIClient()
        payload = self._register_payload({"password": "123"})
        response = client.post("/api/accounts/register/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =====================================================================
#  EMAIL VERIFICATION
# =====================================================================


class EmailVerificationTests(AuthTestCaseBase):

    def setUp(self):
        super().setUp()
        # Prepare an unverified user with a verification token
        self.unverified_user = User.objects.create_user(
            email="unverified@test.com",
            username="unverified",
            password="testpass123",
            role="vendor",
            email_verified=False,
        )
        self.unverified_user.email_verification_token = "valid-verification-token-123"
        self.unverified_user.save()

    def test_verify_email_success(self):
        """Valid token marks email as verified."""
        client = APIClient()
        response = client.post(
            "/api/accounts/verify-email/",
            {"token": "valid-verification-token-123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Email verified", response.data["message"])

        # DB state
        self.unverified_user.refresh_from_db()
        self.assertTrue(self.unverified_user.email_verified)
        self.assertIsNone(self.unverified_user.email_verification_token)

    def test_verify_email_invalid_token(self):
        """Invalid token returns 400."""
        client = APIClient()
        response = client.post(
            "/api/accounts/verify-email/",
            {"token": "nonexistent-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_email_already_verified(self):
        """Already verified email returns success message."""
        self.unverified_user.email_verified = True
        self.unverified_user.save()

        client = APIClient()
        response = client.post(
            "/api/accounts/verify-email/",
            {"token": "valid-verification-token-123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("already verified", response.data["message"])

    def test_verify_email_missing_token(self):
        """Missing token returns 400."""
        client = APIClient()
        response = client.post(
            "/api/accounts/verify-email/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token is required", str(response.data))


# =====================================================================
#  RESEND VERIFICATION
# =====================================================================


class ResendVerificationTests(AuthTestCaseBase):

    def setUp(self):
        super().setUp()
        self.unverified_user = User.objects.create_user(
            email="unverified@test.com",
            username="unverified",
            password="testpass123",
            role="vendor",
            email_verified=False,
        )

    @patch("apps.accounts.views.send_verification_email")
    def test_resend_verification_success(self, mock_send):
        """Resending verification to an unverified user succeeds."""
        client = APIClient()
        response = client.post(
            "/api/accounts/resend-verification/",
            {"email": "unverified@test.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Verification email sent", response.data["message"])
        mock_send.assert_called_once()

    def test_resend_verification_already_verified(self):
        """Already verified user gets appropriate message."""
        self.unverified_user.email_verified = True
        self.unverified_user.save()

        client = APIClient()
        response = client.post(
            "/api/accounts/resend-verification/",
            {"email": "unverified@test.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("already verified", response.data["message"])

    def test_resend_verification_nonexistent_email(self):
        """Non-existent email returns generic message (security)."""
        client = APIClient()
        response = client.post(
            "/api/accounts/resend-verification/",
            {"email": "nobody@test.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Generic response to prevent email enumeration
        self.assertIn("verification link was sent", response.data["message"])

    def test_resend_verification_missing_email(self):
        """Missing email returns 400."""
        client = APIClient()
        response = client.post(
            "/api/accounts/resend-verification/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =====================================================================
#  PASSWORD RESET
# =====================================================================


class PasswordResetTests(AuthTestCaseBase):

    @patch("apps.accounts.views.send_password_reset_email")
    def test_password_reset_request_success(self, mock_send):
        """Requesting password reset for existing email sends email."""
        client = APIClient()
        response = client.post(
            "/api/accounts/password-reset/request/",
            {"email": "user@test.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("reset link was sent", response.data["message"])
        mock_send.assert_called_once()

    def test_password_reset_request_nonexistent_email(self):
        """Non-existent email returns generic message (security)."""
        client = APIClient()
        response = client.post(
            "/api/accounts/password-reset/request/",
            {"email": "nobody@test.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Generic response to prevent email enumeration
        self.assertIn("reset link was sent", response.data["message"])

    def test_password_reset_request_missing_email(self):
        """Missing email returns 400."""
        client = APIClient()
        response = client.post(
            "/api/accounts/password-reset/request/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_reset_confirm_success(self):
        """Valid token + new password resets the password."""
        # Set up a reset token on the user
        self.user.password_reset_token = "valid-reset-token-456"
        self.user.password_reset_token_expires_at = timezone.now() + timedelta(hours=1)
        self.user.save()

        client = APIClient()
        response = client.post(
            "/api/accounts/password-reset/confirm/",
            {"token": "valid-reset-token-456", "password": "NewSecurePass789!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Password reset successfully", response.data["message"])

        # Verify password actually changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewSecurePass789!"))

        # Token should be cleared
        self.assertIsNone(self.user.password_reset_token)
        self.assertIsNone(self.user.password_reset_token_expires_at)

    def test_password_reset_confirm_invalid_token(self):
        """Invalid token returns 400."""
        client = APIClient()
        response = client.post(
            "/api/accounts/password-reset/confirm/",
            {"token": "nonexistent-token", "password": "NewPass789!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_reset_confirm_expired_token(self):
        """Expired token returns 400."""
        self.user.password_reset_token = "expired-reset-token"
        self.user.password_reset_token_expires_at = timezone.now() - timedelta(hours=1)
        self.user.save()

        client = APIClient()
        response = client.post(
            "/api/accounts/password-reset/confirm/",
            {"token": "expired-reset-token", "password": "NewPass789!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired", str(response.data).lower())

    def test_password_reset_confirm_missing_fields(self):
        """Missing token or password returns 400."""
        client = APIClient()
        response = client.post(
            "/api/accounts/password-reset/confirm/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token and password are required", str(response.data))


# =====================================================================
#  ME ENDPOINT
# =====================================================================


class MeEndpointTests(AuthTestCaseBase):

    def test_me_authenticated(self):
        """Authenticated user can retrieve their profile."""
        client = self._client(self.user)
        response = client.get("/api/accounts/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "user@test.com")
        self.assertEqual(response.data["username"], "testuser")
        self.assertEqual(response.data["role"], "vendor")
        self.assertIn("id", response.data)
        self.assertIn("phone_number", response.data)
        self.assertIn("email_verified", response.data)

    def test_me_unauthenticated(self):
        """Unauthenticated request returns 401."""
        client = APIClient()
        response = client.get("/api/accounts/me/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# =====================================================================
#  JWT AUTH
# =====================================================================


class JWTAuthTests(AuthTestCaseBase):

    def test_obtain_token_success(self):
        """Valid credentials return access and refresh tokens."""
        client = APIClient()
        response = client.post(
            "/api/auth/token/",
            {"email": "user@test.com", "password": "securepass123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_obtain_token_invalid_credentials(self):
        """Invalid credentials return 401."""
        client = APIClient()
        response = client.post(
            "/api/auth/token/",
            {"email": "user@test.com", "password": "wrongpassword"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_success(self):
        """Valid refresh token returns a new access token."""
        client = APIClient()
        refresh = RefreshToken.for_user(self.user)

        response = client.post(
            "/api/auth/token/refresh/",
            {"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_refresh_token_invalid(self):
        """Invalid refresh token returns 401."""
        client = APIClient()
        response = client.post(
            "/api/auth/token/refresh/",
            {"refresh": "invalid-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# =====================================================================
#  PROTECTED ENDPOINT
# =====================================================================


class ProtectedEndpointTests(AuthTestCaseBase):

    def test_protected_vendor_access(self):
        """Vendor role user can access protected endpoint."""
        client = self._client(self.user)
        response = client.get("/api/accounts/protected/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Vendor access granted", response.data["message"])

    def test_protected_unauthenticated(self):
        """Unauthenticated request returns 401."""
        client = APIClient()
        response = client.get("/api/accounts/protected/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
