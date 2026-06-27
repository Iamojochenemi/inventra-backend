from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsAdminOrVendor
from .serializers import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    VerifyEmailSerializer,
)
from .services.auth_service import (
    reset_password,
    send_password_reset_email,
    send_verification_email,
    verify_email,
)

User = get_user_model()


@extend_schema(
    tags=["Auth"],
    summary="Register a new user",
    description="Creates a user account and sends a verification email.",
    responses={
        201: RegisterSerializer,
        400: OpenApiResponse(description="Validation error"),
    },
)
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


@extend_schema(
    tags=["Auth"],
    summary="Get current user",
    responses={
        200: OpenApiResponse(
            response={
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "email": {"type": "string"},
                    "username": {"type": "string"},
                    "role": {"type": "string"},
                    "phone_number": {"type": "string"},
                    "email_verified": {"type": "boolean"},
                },
            }
        )
    },
)
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role,
                "phone_number": user.phone_number,
                "email_verified": user.email_verified,
            }
        )


@extend_schema(
    tags=["Auth"],
    summary="Test protected access",
    responses={200: OpenApiResponse(description="Success")},
)
class TestProtectedView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrVendor]

    def get(self, request):
        return Response(
            {
                "message": "Vendor access granted",
                "user": request.user.email,
                "role": request.user.role,
            }
        )


@extend_schema(
    tags=["Auth"],
    summary="Verify email",
    description="Verify a user's email address using a token sent via email.",
    request=VerifyEmailSerializer,
    responses={
        200: OpenApiResponse(description="Email verified successfully"),
        400: OpenApiResponse(description="Invalid or expired token"),
    },
)
class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("token")
        if not token:
            return Response({"error": "token is required"}, status=400)

        success, user, message = verify_email(token)
        if not success:
            return Response({"error": message}, status=400)

        return Response({"message": message, "email": user.email})


@extend_schema(
    tags=["Auth"],
    summary="Resend verification email",
    description="Resend the email verification link to a user's email address.",
    request=ResendVerificationSerializer,
    responses={
        200: OpenApiResponse(
            description="Verification email sent (or email already verified)"
        ),
        400: OpenApiResponse(description="Email is required"),
    },
)
class ResendVerificationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"error": "email is required"}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"message": "If the email exists, a verification link was sent."}
            )

        if user.email_verified:
            return Response({"message": "Email already verified"})

        send_verification_email(user, request)
        return Response({"message": "Verification email sent"})


@extend_schema(
    tags=["Auth"],
    summary="Request password reset",
    description="Send a password reset email to the given email address if it exists.",
    request=PasswordResetRequestSerializer,
    responses={
        200: OpenApiResponse(description="If the email exists, a reset link was sent"),
        400: OpenApiResponse(description="Email is required"),
    },
)
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"error": "email is required"}, status=400)

        try:
            user = User.objects.get(email=email)
            send_password_reset_email(user, request)
        except User.DoesNotExist:
            pass

        return Response({"message": "If the email exists, a reset link was sent."})


@extend_schema(
    tags=["Auth"],
    summary="Confirm password reset",
    description="Reset the password using a valid reset token.",
    request=PasswordResetConfirmSerializer,
    responses={
        200: OpenApiResponse(description="Password has been reset successfully"),
        400: OpenApiResponse(description="Invalid or expired token"),
    },
)
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("token")
        new_password = request.data.get("password")

        if not token or not new_password:
            return Response(
                {"error": "token and password are required"},
                status=400,
            )

        success, user, message = reset_password(token, new_password)
        if not success:
            return Response({"error": message}, status=400)

        return Response({"message": message, "email": user.email})
