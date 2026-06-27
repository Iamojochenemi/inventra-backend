from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.vendors.services import (
    accept_invitation,
    create_invitation,
    reject_invitation,
    resend_invitation,
)
from apps.vendors.services.access_service import validate_vendor_access
from apps.vendors.services.vendor_service import get_user_vendors
from apps.vendors.tasks import send_vendor_invitation_email_task

from .models import Branch, Vendor, VendorInvitation, VendorSettings, VendorStaff
from .serializers import (
    AcceptInvitationSerializer,
    BranchSerializer,
    RejectInvitationSerializer,
    VendorInvitationCreateSerializer,
    VendorInvitationSerializer,
    VendorSerializer,
    VendorSettingsSerializer,
    VendorStaffSerializer,
)


# ------------------------
# VENDORS
# ------------------------
@extend_schema(
    tags=["Vendors"],
    summary="List Vendors",
    description="Retrieve all vendors accessible to the authenticated user.",
    responses={200: VendorSerializer(many=True)},
)
class VendorListView(generics.ListAPIView):
    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return get_user_vendors(self.request.user)


@extend_schema(
    tags=["Vendors"],
    summary="Create Vendor",
    description="Create a new vendor account.",
    responses={
        201: VendorSerializer,
        400: OpenApiResponse(description="Validation error"),
    },
)
class VendorCreateView(generics.CreateAPIView):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated]


# ------------------------
# STAFF
# ------------------------
@extend_schema(
    tags=["Vendors"],
    summary="Add Vendor Staff",
    description="Add a staff member to a vendor (owner only).",
    responses={
        201: VendorStaffSerializer,
        403: OpenApiResponse(description="Permission denied"),
    },
)
class VendorStaffCreateView(generics.CreateAPIView):
    serializer_class = VendorStaffSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        vendor = serializer.validated_data["vendor"]

        validate_vendor_access(
            vendor=vendor,
            user=self.request.user,
            allowed_roles=["owner"],
        )

        serializer.save()


@extend_schema(
    tags=["Vendors"],
    summary="List Vendor Staff",
    description="Retrieve all staff members for a vendor.",
    parameters=[
        OpenApiParameter(
            name="vendor_id",
            type=int,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Vendor ID",
        ),
    ],
    responses={200: VendorStaffSerializer(many=True)},
)
class VendorStaffListView(generics.ListAPIView):
    serializer_class = VendorStaffSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        vendor_id = self.request.query_params.get("vendor_id")
        if not vendor_id:
            return VendorStaff.objects.none()

        vendor = get_object_or_404(Vendor, id=vendor_id)
        validate_vendor_access(vendor=vendor, user=self.request.user)

        return vendor.staff.select_related("user", "branch").all()


# ------------------------
# BRANCHES
# ------------------------
@extend_schema(
    tags=["Vendors"],
    summary="Create Branch",
    description="Create a branch under a vendor.",
    responses={201: BranchSerializer},
)
class BranchCreateView(generics.CreateAPIView):
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        vendor = serializer.validated_data["vendor"]

        validate_vendor_access(
            vendor=vendor,
            user=self.request.user,
            allowed_roles=["owner", "manager"],
        )

        serializer.save()


@extend_schema(
    tags=["Vendors"],
    summary="List Branches",
    description="List all branches for a vendor.",
    parameters=[
        OpenApiParameter(
            name="vendor_id",
            type=int,
            location=OpenApiParameter.QUERY,
            required=True,
        ),
    ],
    responses={200: BranchSerializer(many=True)},
)
class BranchListView(generics.ListAPIView):
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        vendor_id = self.request.query_params.get("vendor_id")
        if not vendor_id:
            return Branch.objects.none()

        vendor = get_object_or_404(Vendor, id=vendor_id)
        validate_vendor_access(vendor=vendor, user=self.request.user)

        return vendor.branches.all()


# ------------------------
# SETTINGS
# ------------------------
@extend_schema(
    tags=["Vendors"],
    summary="Retrieve/Update Vendor Settings",
    description="Get or update settings for a vendor.",
    responses={200: VendorSettingsSerializer},
)
class VendorSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = VendorSettingsSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        vendor = get_object_or_404(
            get_user_vendors(self.request.user),
            id=self.kwargs["vendor_id"],
        )

        validate_vendor_access(
            vendor=vendor,
            user=self.request.user,
            allowed_roles=["owner", "manager"],
        )

        settings, _ = VendorSettings.objects.get_or_create(vendor=vendor)
        return settings


# ------------------------
# INVITATIONS
# ------------------------
@extend_schema(
    tags=["Vendors"],
    summary="Create Invitation",
    description="Invite a user to join a vendor.",
    request=VendorInvitationCreateSerializer,
    responses={
        201: VendorInvitationSerializer,
        400: OpenApiResponse(description="Validation error or invitation failed"),
    },
)
class InvitationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VendorInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        vendor = serializer.validated_data["vendor"]

        validate_vendor_access(
            vendor=vendor,
            user=request.user,
            allowed_roles=["owner", "manager"],
        )

        try:
            invitation = create_invitation(
                vendor=vendor,
                email=serializer.validated_data["email"],
                role=serializer.validated_data["role"],
                created_by=request.user,
                request=request,
            )
            send_vendor_invitation_email_task.delay(invitation.id)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        return Response(
            VendorInvitationSerializer(invitation).data,
            status=201,
        )


@extend_schema(
    tags=["Vendors"],
    summary="List Invitations",
    description="List all invitations for a vendor.",
    responses={200: VendorInvitationSerializer(many=True)},
)
class InvitationListView(generics.ListAPIView):
    serializer_class = VendorInvitationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        vendor_id = self.request.query_params.get("vendor_id")
        if not vendor_id:
            return VendorInvitation.objects.none()

        vendor = get_object_or_404(Vendor, id=vendor_id)

        validate_vendor_access(
            vendor=vendor,
            user=self.request.user,
            allowed_roles=["owner", "manager"],
        )

        return vendor.invitations.all()


# ------------------------
# PUBLIC INVITATION ACTIONS
# ------------------------
@extend_schema(
    tags=["Vendors"],
    summary="Accept Invitation",
    description="Accept a vendor invitation using a token.",
    request=AcceptInvitationSerializer,
    responses={200: OpenApiResponse(description="Invitation accepted")},
)
class AcceptInvitationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        success, vendor_staff, message = accept_invitation(
            token=serializer.validated_data["token"],
            password=serializer.validated_data.get("password") or None,
        )

        if not success:
            return Response({"error": message}, status=400)

        return Response(
            {
                "message": message,
                "vendor_id": vendor_staff.vendor_id,
                "role": vendor_staff.role,
            }
        )


@extend_schema(
    tags=["Vendors"],
    summary="Reject Invitation",
    description="Reject a vendor invitation using a token.",
    request=RejectInvitationSerializer,
    responses={200: OpenApiResponse(description="Invitation rejected")},
)
class RejectInvitationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RejectInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        success, message = reject_invitation(serializer.validated_data["token"])

        if not success:
            return Response({"error": message}, status=400)

        return Response({"message": message})


@extend_schema(
    tags=["Vendors"],
    summary="Resend Invitation",
    description="Resend a pending vendor invitation.",
    request=None,
    responses={
        200: OpenApiResponse(description="Invitation resent"),
        400: OpenApiResponse(description="Failed to resend invitation"),
        404: OpenApiResponse(description="Invitation not found"),
    },
)
class ResendInvitationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        invitation = get_object_or_404(VendorInvitation, pk=pk)

        validate_vendor_access(
            vendor=invitation.vendor,
            user=request.user,
            allowed_roles=["owner", "manager"],
        )

        if not resend_invitation(invitation.id):
            return Response({"error": "Failed to resend invitation"}, status=400)

        return Response({"message": "Invitation resent"})
