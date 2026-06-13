from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Vendor, VendorStaff, Branch

from .serializers import (
    VendorSerializer,
    VendorStaffSerializer,
    BranchSerializer
)

from .services import validate_vendor_access


class VendorCreateView(generics.CreateAPIView):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated]


class VendorStaffCreateView(generics.CreateAPIView):
    serializer_class = VendorStaffSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        vendor = serializer.validated_data["vendor"]

        # 🔒 only owners can add staff
        validate_vendor_access(
            vendor=vendor,
            user=self.request.user,
            allowed_roles=["owner"]
        )

        serializer.save()


class BranchCreateView(generics.CreateAPIView):
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        vendor = serializer.validated_data["vendor"]

        # 🔒 only owners and managers can create branches
        validate_vendor_access(
            vendor=vendor,
            user=self.request.user,
            allowed_roles=["owner", "manager"]
        )

        serializer.save()