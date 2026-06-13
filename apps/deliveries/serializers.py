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