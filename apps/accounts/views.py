from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import get_user_model

from .serializers import RegisterSerializer
from .permissions import IsAdminOrVendor
from .services.auth_service import (
    send_verification_email,
    verify_email,
    send_password_reset_email,
    reset_password,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


from drf_spectacular.utils import extend_schema, OpenApiResponse

@extend_schema(
    tags=["Auth"],
    summary="Get current user",
    responses={
        200: OpenApiResponse(
            response={
                "id": int,
                "email": str,
                "username": str,
                "role": str,
                "phone_number": str,
                "email_verified": bool,
            }
        )
    },
)
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "role": user.role,
            "phone_number": user.phone_number,
            "email_verified": user.email_verified,
        })


@extend_schema(
    tags=["Auth"],
    summary="Test protected access",
    responses={200: OpenApiResponse(description="Success")},
)
class TestProtectedView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrVendor]

    def get(self, request):
        return Response({
            "message": "Vendor access granted",
            "user": request.user.email,
            "role": request.user.role,
        })


@extend_schema(
    tags=["Auth"],
    summary="Verify email",
    request={
        "type": "object",
        "properties": {
            "token": {"type": "string"}
        },
        "required": ["token"],
    },
    responses={200: OpenApiResponse(description="Email verified")},
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
    request={
        "type": "object",
        "properties": {
            "email": {"type": "string"}
        },
        "required": ["email"],
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
            return Response({"message": "If the email exists, a verification link was sent."})

        if user.email_verified:
            return Response({"message": "Email already verified"})

        send_verification_email(user, request)
        return Response({"message": "Verification email sent"})


@extend_schema(
    tags=["Auth"],
    summary="Request password reset",
    request={
        "type": "object",
        "properties": {
            "email": {"type": "string"}
        },
        "required": ["email"],
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
    request={
        "type": "object",
        "properties": {
            "token": {"type": "string"},
            "password": {"type": "string"},
        },
        "required": ["token", "password"],
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
