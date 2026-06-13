from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

from .models import Order, OrderStatusLog
from .serializers import (
    OrderSerializer,
    OrderStatusUpdateSerializer
)
from apps.inventory.models import Inventory
from apps.deliveries.services import create_delivery_from_order
from apps.notifications.tasks import send_notification_task


class OrderCreateView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user

        staff = user.vendorstaff_set.first()

        if not staff:
            raise PermissionDenied("You are not assigned to any vendor.")

        if staff.role not in ["owner", "manager"]:
            raise PermissionDenied("You are not allowed to create orders.")

        serializer.save(created_by=user)


class OrderStatusUpdateView(generics.GenericAPIView):
    serializer_class = OrderStatusUpdateSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        old_status = order.status

        allowed = order.ALLOWED_TRANSITIONS.get(old_status, [])

        if new_status not in allowed:
            return Response(
                {
                    "error": f"Cannot change status from '{old_status}' to '{new_status}'",
                    "allowed_statuses": allowed
                },
                status=400
            )

        with transaction.atomic():

            # restore stock on cancel
            if new_status == "cancelled" and old_status in ["pending", "confirmed"]:
                for item in order.items.select_related("product").all():

                    inventory = Inventory.objects.select_for_update().filter(
                        product=item.product,
                        branch=order.branch
                    ).first()

                    if inventory:
                        inventory.quantity += item.quantity
                        inventory.save()

            order.status = new_status
            order.save()

            # Audit log
            OrderStatusLog.objects.create(
                order=order,
                previous_status=old_status,
                new_status=new_status,
                changed_by=request.user
            )

            # Create delivery
            if new_status == "confirmed" and old_status == "pending":
                create_delivery_from_order(order)

            # Async notification
            send_notification_task.delay(
                vendor_id=order.vendor.id,
                notification_type="order",
                title="Order Status Updated",
                message=(
                    f"Order #{order.id} "
                    f"changed from '{old_status}' to '{new_status}'."
                )
            )

        return Response(
            {
                "message": "Order status updated.",
                "order_id": order.id,
                "status": order.status,
            }
        )