from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Delivery, DeliveryLog
from .serializers import DeliverySerializer
from apps.vendors.models import VendorStaff
from apps.notifications.services import create_notification


class DeliveryViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = Delivery.objects.select_related(
        "order",
        "assigned_rider"
    ).all()

    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]

    # -------------------------
    # ROLE + TENANT SAFE STAFF RESOLUTION
    # -------------------------
    def get_staff(self, user, delivery):
        """
        Get staff record scoped to the delivery's vendor.
        Prevents cross-vendor access issues.
        """
        return user.vendorstaff_set.filter(
            vendor=delivery.order.vendor
        ).first()

    # -------------------------
    # ASSIGN RIDER (DISPATCHER ONLY)
    # -------------------------
    @action(detail=True, methods=["post"])
    def assign_rider(self, request, pk=None):

        delivery = self.get_object()
        staff = self.get_staff(request.user, delivery)

        if not staff or staff.role != "dispatcher":
            return Response(
                {"error": "Only dispatchers can assign riders"},
                status=403
            )

        rider_id = request.data.get("rider_id")
        rider = get_object_or_404(VendorStaff, id=rider_id)

        old_rider = delivery.assigned_rider

        delivery.assigned_rider = rider
        delivery.status = "assigned"
        delivery.save()

        DeliveryLog.objects.create(
            delivery=delivery,
            event_type="rider_assignment",
            previous_value=str(old_rider.id) if old_rider else "",
            new_value=str(rider.id),
            changed_by=request.user
        )

        # -------------------------
        # NOTIFICATION
        # -------------------------
        create_notification(
            user=delivery.order.created_by,
            type="delivery",
            title="Rider Assigned",
            message=f"Rider has been assigned to Order #{delivery.order.id}"
        )

        return Response({
            "message": "Rider assigned successfully",
            "delivery_id": delivery.id,
            "rider_id": rider.id,
            "status": delivery.status
        })

    # -------------------------
    # UPDATE DELIVERY STATUS (RIDER ONLY)
    # -------------------------
    @action(detail=True, methods=["post"])
    def update_status(self, request, pk=None):

        delivery = self.get_object()
        staff = self.get_staff(request.user, delivery)

        if not staff or staff.role != "rider":
            return Response(
                {"error": "Only riders can update delivery status"},
                status=403
            )

        new_status = request.data.get("status")
        recipient_name = request.data.get("recipient_name", "")

        if new_status not in dict(Delivery.STATUS_CHOICES):
            return Response(
                {"error": "Invalid status"},
                status=400
            )

        old_status = delivery.status

        allowed = Delivery.ALLOWED_TRANSITIONS.get(old_status, [])

        if new_status not in allowed:
            return Response(
                {
                    "error": f"Cannot change from '{old_status}' to '{new_status}'",
                    "allowed": allowed
                },
                status=400
            )

        delivery.status = new_status

        # -------------------------
        # DELIVERY COMPLETION (PROOF)
        # -------------------------
        if new_status == "delivered":
            delivery.delivered_at = timezone.now()

            if recipient_name:
                delivery.recipient_name = recipient_name

            # optional: notify order creator on completion
            create_notification(
                user=delivery.order.created_by,
                type="delivery",
                title="Delivery Completed",
                message=f"Order #{delivery.order.id} has been delivered successfully"
            )

        delivery.save()

        DeliveryLog.objects.create(
            delivery=delivery,
            event_type="status_change",
            previous_value=old_status,
            new_value=new_status,
            changed_by=request.user
        )

        return Response({
            "message": "Status updated successfully",
            "delivery_id": delivery.id,
            "old_status": old_status,
            "new_status": new_status,
            "recipient_name": delivery.recipient_name,
            "delivered_at": delivery.delivered_at
        })