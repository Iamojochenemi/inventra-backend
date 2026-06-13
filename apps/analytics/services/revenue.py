from django.db.models import Sum, Count
from apps.orders.models import Order


def get_revenue_intelligence(vendor):
    orders = Order.objects.filter(vendor=vendor, status="completed")

    total_revenue = orders.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    total_orders = orders.count()

    avg_order_value = (
        total_revenue / total_orders
        if total_orders else 0
    )

    return {
        "total_revenue": float(total_revenue),
        "total_orders": total_orders,
        "average_order_value": float(avg_order_value)
    }