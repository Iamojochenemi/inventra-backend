from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction

from .models import (
    Category,
    Product,
    Inventory,
    InventoryLog,
)
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    InventoryAdjustmentSerializer,
    InventorySerializer,
)
from .services import initialize_product_inventory

from apps.vendors.services import validate_vendor_access


# ------------------------
# CATEGORY
# ------------------------
class CategoryCreateView(generics.CreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        vendor = serializer.validated_data["vendor"]

        validate_vendor_access(
            vendor=vendor,
            user=self.request.user,
            allowed_roles=["owner", "manager"]
        )

        serializer.save(vendor=vendor)


# ------------------------
# PRODUCT
# ------------------------
class ProductCreateView(generics.CreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        vendor = serializer.validated_data["vendor"]

        validate_vendor_access(
            vendor=vendor,
            user=self.request.user,
            allowed_roles=["owner", "manager"]
        )

        category = serializer.validated_data.get("category")

        if category and category.vendor != vendor:
            raise serializers.ValidationError(
                "Category does not belong to this vendor."
            )

        product = serializer.save(vendor=vendor)

        initialize_product_inventory(product)


# ------------------------
# INVENTORY ADJUSTMENT
# ------------------------
class InventoryAdjustmentView(generics.GenericAPIView):
    serializer_class = InventoryAdjustmentSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        inventory_id = serializer.validated_data["inventory_id"]
        change_quantity = serializer.validated_data["change_quantity"]
        adjustment_type = serializer.validated_data["adjustment_type"]
        reason = serializer.validated_data.get("reason", "")

        inventory = Inventory.objects.get(id=inventory_id)

        validate_vendor_access(
            vendor=inventory.product.vendor,
            user=request.user,
            allowed_roles=[
                "owner",
                "manager",
                "inventory",
            ]
        )

        with transaction.atomic():

            log = InventoryLog.objects.create(
                inventory=inventory,
                change_quantity=change_quantity,
                adjustment_type=adjustment_type,
                reason=reason,
                created_by=request.user
            )

            result = log.apply_inventory_change()

            inventory = result["inventory"]

        return Response(
            {
                "message": "Inventory updated successfully",
                "inventory_id": inventory.id,
                "new_quantity": inventory.quantity,
                "is_low_stock": result["is_low_stock"],
            },
            status=200
        )


# ------------------------
# INVENTORY
# ------------------------
class InventoryListView(generics.ListAPIView):
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Inventory.objects.filter(
            product__vendor__staff__user=self.request.user
        )

        branch_id = self.request.query_params.get("branch")

        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)

        product_id = self.request.query_params.get("product")

        if product_id:
            queryset = queryset.filter(product_id=product_id)

        return queryset