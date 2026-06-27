from rest_framework import serializers

from apps.orders.models import Order

from .services import create_payment_for_order


class PaymentInitializeSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()

    def validate_order_id(self, value):
        try:
            order = Order.objects.get(id=value)
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found.")

        if order.status != "pending":
            raise serializers.ValidationError("Only pending orders can be paid.")

        return value

    def create(self, validated_data):
        order = Order.objects.get(id=validated_data["order_id"])
        payment = create_payment_for_order(order)

        return payment
