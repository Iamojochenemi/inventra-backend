from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiParameter

from apps.common.mixins import TenantIsolationMixin

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
@extend_schema_view(
    post=extend_schema(
        tags=["Inventory"],
        summary="Create Category",
        description="Create a product category under a vendor.",
        responses={
            201: CategorySerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied"),
        },
    )
)
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
@extend_schema_view(
    post=extend_schema(
        tags=["Inventory"],
        summary="Create Product",
        description="Create a product and initialize its inventory across branches.",
        responses={
            201: ProductSerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied"),
        },
    )
)
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
@extend_schema_view(
    post=extend_schema(
        tags=["Inventory"],
        summary="Adjust Inventory",
        description="Increase or decrease product stock and log the change.",
        request=InventoryAdjustmentSerializer,
        responses={
            200: OpenApiResponse(description="Inventory updated successfully"),
            400: OpenApiResponse(description="Invalid adjustment request"),
            403: OpenApiResponse(description="Permission denied"),
        },
    )
)
class InventoryAdjustmentView(TenantIsolationMixin, generics.GenericAPIView):
    tenant_vendor_field = "product__vendor"
    serializer_class = InventoryAdjustmentSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        inventory_id = serializer.validated_data["inventory_id"]
        change_quantity = serializer.validated_data["change_quantity"]
        adjustment_type = serializer.validated_data["adjustment_type"]
        reason = serializer.validated_data.get("reason", "")

        inventory = get_object_or_404(
            self.scope_queryset(
                Inventory.objects.select_related("product__vendor"),
            ),
            id=inventory_id,
        )

        validate_vendor_access(
            vendor=inventory.product.vendor,
            user=request.user,
            allowed_roles=[
                "owner",
                "manager",
                "inventory",
            ]
        )

        old_quantity = inventory.quantity

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

            from apps.audit_logs.services import create_audit_log

            create_audit_log(
                user=request.user,
                obj=inventory,
                action="update",
                old_values={"quantity": old_quantity},
                new_values={
                    "quantity": inventory.quantity,
                    "adjustment_type": adjustment_type,
                    "reason": reason,
                },
                reason="Inventory adjustment"
            )

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
# INVENTORY LIST
# ------------------------
@extend_schema_view(
    get=extend_schema(
        tags=["Inventory"],
        summary="List Inventory",
        description="List all inventory records accessible to the authenticated user.",
        parameters=[
            OpenApiParameter(
                name="branch",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by branch ID",
            ),
            OpenApiParameter(
                name="product",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by product ID",
            ),
        ],
        responses={
            200: InventorySerializer(many=True),
        },
    )
)
class InventoryListView(TenantIsolationMixin, generics.ListAPIView):
    tenant_vendor_field = "product__vendor"
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = self.scope_queryset(Inventory.objects.all())

        branch_id = self.request.query_params.get("branch")
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)

        product_id = self.request.query_params.get("product")
        if product_id:
            queryset = queryset.filter(product_id=product_id)

        return queryset