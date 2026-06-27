from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit_logs.services import create_audit_log
from apps.common.mixins import TenantIsolationMixin
from apps.notifications.services import create_notification
from apps.vendors.models import VendorStaff

from .models import Delivery, DeliveryLog
from .serializers import (
    AssignRiderSerializer,
    DeliverySerializer,
    UpdateDeliveryStatusSerializer,
)


@extend_schema_view(
    list=extend_schema(
        tags=["Deliveries"],
        summary="List deliveries",
        description="List all deliveries accessible to the authenticated user.",
        responses={
            200: DeliverySerializer(many=True),
        },
    ),
    retrieve=extend_schema(
        tags=["Deliveries"],
        summary="Retrieve delivery",
        description="Retrieve a single delivery by ID.",
        responses={
            200: DeliverySerializer,
            404: OpenApiResponse(description="Delivery not found"),
        },
    ),
    assign_rider=extend_schema(
        tags=["Deliveries"],
        summary="Assign rider",
        description="Assign a rider to a delivery (dispatcher only).",
        request=AssignRiderSerializer,
        responses={
            200: OpenApiResponse(description="Rider assigned successfully"),
            403: OpenApiResponse(description="Only dispatchers can assign riders"),
            404: OpenApiResponse(description="Delivery or rider not found"),
        },
    ),
    update_status=extend_schema(
        tags=["Deliveries"],
        summary="Update delivery status",
        description="Update delivery status (rider only). Allowed transitions: pending→assigned→in_transit→delivered.",
        request=UpdateDeliveryStatusSerializer,
        responses={
            200: OpenApiResponse(description="Status updated successfully"),
            400: OpenApiResponse(
                description="Invalid status or transition not allowed"
            ),
            403: OpenApiResponse(description="Only riders can update delivery status"),
            404: OpenApiResponse(description="Delivery not found"),
        },
    ),
)
class DeliveryViewSet(TenantIsolationMixin, viewsets.ReadOnlyModelViewSet):
    tenant_vendor_field = "order__vendor"
    lookup_field = "id"
    lookup_value_regex = "[0-9]+"
    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.scope_queryset(
            Delivery.objects.select_related(
                "order",
                "assigned_rider",
            )
        ).distinct()

    def get_staff(self, user, delivery):
        return user.vendorstaff_set.filter(vendor=delivery.order.vendor).first()

    # -------------------------
    # ASSIGN RIDER
    # -------------------------
    @action(detail=True, methods=["post"])
    def assign_rider(self, request, pk=None):

        delivery = self.get_object()
        staff = self.get_staff(request.user, delivery)

        if not staff or staff.role != "dispatcher":
            return Response({"error": "Only dispatchers can assign riders"}, status=403)

        rider_id = request.data.get("rider_id")
        rider = get_object_or_404(VendorStaff, id=rider_id)

        old_rider = delivery.assigned_rider

        delivery.assigned_rider = rider
        delivery.status = "assigned"
        delivery.save()

        # -------------------------
        # DELIVERY LOG
        # -------------------------
        DeliveryLog.objects.create(
            delivery=delivery,
            event_type="rider_assignment",
            previous_value=str(old_rider.id) if old_rider else "",
            new_value=str(rider.id),
            changed_by=request.user,
        )

        # -------------------------
        # AUDIT LOG (NEW)
        # -------------------------
        create_audit_log(
            user=request.user,
            obj=delivery,
            action="update",
            old_values={
                "assigned_rider": old_rider.id if old_rider else None,
                "status": "pending",
            },
            new_values={"assigned_rider": rider.id, "status": "assigned"},
            reason="Rider assigned to delivery",
        )

        # -------------------------
        # NOTIFICATION
        # -------------------------
        create_notification(
            user=delivery.order.created_by,
            type="delivery",
            title="Rider Assigned",
            message=f"Rider has been assigned to Order #{delivery.order.id}",
        )

        return Response(
            {
                "message": "Rider assigned successfully",
                "delivery_id": delivery.id,
                "rider_id": rider.id,
                "status": delivery.status,
            }
        )

    # -------------------------
    # UPDATE DELIVERY STATUS
    # -------------------------
    @action(detail=True, methods=["post"])
    def update_status(self, request, pk=None):

        delivery = self.get_object()
        staff = self.get_staff(request.user, delivery)

        if not staff or staff.role != "rider":
            return Response(
                {"error": "Only riders can update delivery status"}, status=403
            )

        new_status = request.data.get("status")
        recipient_name = request.data.get("recipient_name", "")

        if new_status not in dict(Delivery.STATUS_CHOICES):
            return Response({"error": "Invalid status"}, status=400)

        old_status = delivery.status

        allowed = Delivery.ALLOWED_TRANSITIONS.get(old_status, [])

        if new_status not in allowed:
            return Response(
                {
                    "error": f"Cannot change from '{old_status}' to '{new_status}'",
                    "allowed": allowed,
                },
                status=400,
            )

        delivery.status = new_status

        if new_status == "delivered":
            delivery.delivered_at = timezone.now()

            if recipient_name:
                delivery.recipient_name = recipient_name

            create_notification(
                user=delivery.order.created_by,
                type="delivery",
                title="Delivery Completed",
                message=f"Order #{delivery.order.id} has been delivered successfully",
            )

        delivery.save()

        # -------------------------
        # DELIVERY LOG
        # -------------------------
        DeliveryLog.objects.create(
            delivery=delivery,
            event_type="status_change",
            previous_value=old_status,
            new_value=new_status,
            changed_by=request.user,
        )

        # -------------------------
        # AUDIT LOG (NEW)
        # -------------------------
        create_audit_log(
            user=request.user,
            obj=delivery,
            action="update",
            old_values={"status": old_status},
            new_values={"status": new_status, "recipient_name": recipient_name},
            reason="Delivery status update",
        )

        return Response(
            {
                "message": "Status updated successfully",
                "delivery_id": delivery.id,
                "old_status": old_status,
                "new_status": new_status,
                "recipient_name": delivery.recipient_name,
                "delivered_at": delivery.delivered_at,
            }
        )
