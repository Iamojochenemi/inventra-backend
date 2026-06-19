from django.db import transaction
from rest_framework import serializers

from .models import Order, OrderItem, OrderStatusLog
from apps.inventory.models import Inventory, Product
from apps.payments.models import Payment


# -----------------------
# ORDER ITEM (READ ONLY)
# -----------------------
class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["product", "quantity", "unit_price"]


# -----------------------
# STATUS LOG (READ ONLY)
# -----------------------
class OrderStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusLog
        fields = [
            "previous_status",
            "new_status",
            "changed_by",
            "created_at",
        ]


# -----------------------
# PAYMENT (READ ONLY)
# -----------------------
class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["reference", "amount", "status", "provider"]


# -----------------------
# ORDER READ SERIALIZER
# -----------------------
class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_logs = OrderStatusLogSerializer(many=True, read_only=True)
    payment = PaymentSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "vendor",
            "branch",
            "customer_name",
            "customer_phone",
            "status",
            "total_amount",
            "items",
            "status_logs",
            "payment",
            "created_at",
        ]
        read_only_fields = ["total_amount"]


# -----------------------
# ORDER CREATE SERIALIZER (CLEAN)
# -----------------------
class OrderCreateSerializer(serializers.ModelSerializer):
    items = serializers.ListField(write_only=True)

    class Meta:
        model = Order
        fields = [
            "branch",
            "customer_name",
            "customer_phone",
            "items",
        ]

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        staff = user.vendorstaff_set.first()

        if not staff:
            raise serializers.ValidationError(
                {"error": "User is not assigned to any vendor."}
            )

        attrs["vendor"] = staff.vendor

        branch = attrs.get("branch")

        if not branch:
            raise serializers.ValidationError(
                {"error": "Branch is required."}
            )

        if branch.vendor != staff.vendor:
            raise serializers.ValidationError(
                {"error": "Branch does not belong to your vendor."}
            )

        items = self.initial_data.get("items")

        if not items or len(items) == 0:
            raise serializers.ValidationError(
                {"error": "Items cannot be empty."}
            )

        return attrs

    def create(self, validated_data):
        from apps.orders.services import create_order_with_items
        from rest_framework.exceptions import ValidationError

        items_data = validated_data.pop("items")

        try:
            return create_order_with_items(
                vendor=validated_data["vendor"],
                branch=validated_data["branch"],
                created_by=self.context["request"].user,
                customer_name=validated_data["customer_name"],
                customer_phone=validated_data["customer_phone"],
                items_data=items_data,
            )

        except ValidationError as e:
            # re-raise DRF validation errors cleanly
            raise e

        except Exception as e:
            # fallback safe API error (prevents HTML crash page)
            raise ValidationError({
                "error": "Order creation failed",
                "details": str(e)
            })


# -----------------------
# STATUS UPDATE
# -----------------------
class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)