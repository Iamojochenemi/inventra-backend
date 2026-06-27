from rest_framework import serializers

from .models import Delivery, DeliveryLog


class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = [
            "id",
            "order",
            "assigned_rider",
            "status",
            "recipient_name",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class DeliveryLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryLog
        fields = [
            "id",
            "delivery",
            "event_type",
            "previous_value",
            "new_value",
            "changed_by",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]


class AssignRiderSerializer(serializers.Serializer):
    rider_id = serializers.IntegerField(
        help_text="ID of the VendorStaff member to assign as rider"
    )


class UpdateDeliveryStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[c[0] for c in Delivery.STATUS_CHOICES],
        help_text="New delivery status",
    )
    recipient_name = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Recipient name (required for 'delivered' status)",
    )
