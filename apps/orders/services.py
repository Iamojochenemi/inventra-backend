from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.orders.models import Order, OrderItem
from apps.inventory.models import Inventory, Product
from apps.audit_logs.services import create_audit_log


def create_order_with_items(*, vendor, branch, created_by, customer_name, customer_phone, items_data):

    with transaction.atomic():
        order = Order.objects.create(
            vendor=vendor,
            branch=branch,
            customer_name=customer_name,
            customer_phone=customer_phone,
            created_by=created_by,
        )

        total = 0

        for item in items_data:
            product = Product.objects.get(id=item["product"])
            quantity = item["quantity"]

            inventory = Inventory.objects.select_for_update().filter(
                product=product,
                branch=branch
            ).first()

            if not inventory:
                raise ValidationError({
                    "error": "No inventory found",
                    "product": product.name,
                    "branch": branch.id
                })

            if inventory.quantity < quantity:
                raise ValidationError({
                    "error": "Insufficient stock",
                    "product": product.name,
                    "requested": quantity,
                    "available": inventory.quantity
                })

            inventory.quantity -= quantity
            inventory.save()

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                unit_price=product.price
            )

            total += quantity * product.price

        order.total_amount = total
        order.save()

        create_audit_log(
            user=created_by,
            obj=order,
            action="create",
            new_values={
                "status": order.status,
                "customer_name": order.customer_name,
                "customer_phone": order.customer_phone,
                "total_amount": str(order.total_amount),
            },
            reason="Order created",
        )

        return order