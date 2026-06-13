from django.db import transaction
from rest_framework import serializers

from .models import Order, OrderItem, OrderStatusLog
from apps.inventory.models import Inventory


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
# ORDER READ SERIALIZER
# -----------------------
class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_logs = OrderStatusLogSerializer(many=True, read_only=True)

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
            "created_at",
        ]


# -----------------------
# ORDER CREATE SERIALIZER
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
            raise serializers.ValidationError("User is not assigned to any vendor.")

        attrs["vendor"] = staff.vendor

        branch = attrs["branch"]

        if branch.vendor != staff.vendor:
            raise serializers.ValidationError("Branch does not belong to your vendor.")

        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop("items")

        with transaction.atomic():
            order = Order.objects.create(**validated_data)

            total = 0

            for item in items_data:
                product = item["product"]
                quantity = item["quantity"]

                unit_price = product.price

                inventory = Inventory.objects.select_for_update().filter(
                    product=product,
                    branch=order.branch
                ).first()

                if not inventory:
                    raise serializers.ValidationError(
                        f"No inventory found for {product.name} in this branch."
                    )

                if inventory.quantity < quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for {product.name}."
                    )

                inventory.quantity -= quantity
                inventory.save()

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price
                )

                total += quantity * unit_price

            order.total_amount = total
            order.save()

            return order


# -----------------------
# STATUS UPDATE
# -----------------------
class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)