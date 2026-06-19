from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
)

from .models import Order, OrderStatusLog
from .serializers import (
    OrderCreateSerializer,
    OrderSerializer,
    OrderStatusUpdateSerializer
)

from apps.inventory.models import Inventory
from apps.deliveries.services import create_delivery_from_order
from apps.notifications.tasks import send_notification_task
from apps.vendors.services import validate_vendor_access
from apps.audit_logs.services import create_audit_log


@extend_schema_view(
    get=extend_schema(
        tags=["Orders"],
        summary="List Orders",
        description="List orders belonging to vendors the authenticated user has access to.",
        parameters=[
            OpenApiParameter(
                name="vendor_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by vendor ID",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by order status",
            ),
        ],
    )
)
class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Order.objects.filter(
            vendor__staff__user=self.request.user,
        ).select_related(
            "vendor",
            "branch",
        ).prefetch_related(
            "items",
            "status_logs",
            "payment",
        ).distinct()

        vendor_id = self.request.query_params.get("vendor_id")
        if vendor_id:
            queryset = queryset.filter(vendor_id=vendor_id)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by("-created_at")


@extend_schema_view(
    get=extend_schema(
        tags=["Orders"],
        summary="Retrieve Order",
        description="Retrieve a single order by ID.",
        responses={
            200: OrderSerializer,
            404: OpenApiResponse(description="Order not found"),
        },
    )
)
class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(
            vendor__staff__user=self.request.user,
        ).select_related(
            "vendor",
            "branch",
        ).prefetch_related(
            "items",
            "status_logs",
            "payment",
        ).distinct()


@extend_schema_view(
    post=extend_schema(
        tags=["Orders"],
        summary="Create Order",
        description="Create an order and automatically generate payment record.",
        request=OrderCreateSerializer,
        responses={
            201: OrderSerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied"),
        },
    )
)
class OrderCreateView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user

        staff = user.vendorstaff_set.first()

        if not staff:
            raise PermissionDenied(
                "You are not assigned to any vendor."
            )

        if staff.role not in ["owner", "manager"]:
            raise PermissionDenied(
                "You are not allowed to create orders."
            )

        order = serializer.save(created_by=user)

        from apps.payments.services import create_payment_for_order
        create_payment_for_order(order)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)

        order = serializer.instance

        return Response(
            OrderSerializer(order).data,
            status=201,
            headers=headers,
        )


@extend_schema_view(
    post=extend_schema(
        tags=["Orders"],
        summary="Update Order Status",
        description="Updates order status and triggers inventory, delivery, and notifications.",
        request=OrderStatusUpdateSerializer,
        responses={
            200: OpenApiResponse(description="Status updated successfully"),
            400: OpenApiResponse(description="Invalid status transition"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Order not found"),
        },
    )
)
class OrderStatusUpdateView(generics.GenericAPIView):
    serializer_class = OrderStatusUpdateSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)

        validate_vendor_access(
            vendor=order.vendor,
            user=request.user,
            allowed_roles=["owner", "manager"],
        )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        old_status = order.status

        allowed = order.ALLOWED_TRANSITIONS.get(
            old_status,
            []
        )

        if new_status not in allowed:
            return Response(
                {
                    "error": (
                        f"Cannot change status from "
                        f"'{old_status}' to '{new_status}'"
                    ),
                    "allowed_statuses": allowed,
                },
                status=400,
            )

        with transaction.atomic():

            if (
                new_status == "cancelled"
                and old_status in ["pending", "confirmed"]
            ):
                for item in order.items.select_related(
                    "product"
                ).all():

                    inventory = (
                        Inventory.objects
                        .select_for_update()
                        .filter(
                            product=item.product,
                            branch=order.branch,
                        )
                        .first()
                    )

                    if inventory:
                        inventory.quantity += item.quantity
                        inventory.save()

            order.status = new_status
            order.save()

            OrderStatusLog.objects.create(
                order=order,
                previous_status=old_status,
                new_status=new_status,
                changed_by=request.user,
            )

            if (
                new_status == "confirmed"
                and old_status == "pending"
            ):
                create_delivery_from_order(order)

            create_audit_log(
                user=request.user,
                obj=order,
                action="update",
                old_values={
                    "status": old_status,
                },
                new_values={
                    "status": new_status,
                },
                ip_address=request.META.get(
                    "REMOTE_ADDR"
                ),
                user_agent=request.META.get(
                    "HTTP_USER_AGENT",
                    "",
                ),
                reason="Order status updated",
            )

            send_notification_task.delay(
                vendor_id=order.vendor.id,
                notification_type="order",
                title="Order Status Updated",
                message=(
                    f"Order #{order.id} "
                    f"changed from '{old_status}' "
                    f"to '{new_status}'."
                ),
            )

        return Response(
            {
                "message": "Order status updated.",
                "order_id": order.id,
                "status": order.status,
            }
        )
