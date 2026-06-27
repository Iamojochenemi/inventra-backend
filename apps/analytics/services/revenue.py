from django.db.models import Count, Q, Sum

from apps.orders.models import Order


def get_revenue_intelligence(vendor):
    """
    Aggregate revenue and order metrics in a single database pass.

    Uses conditional Sum/Count with filter kwargs to compute all status
    breakdowns without separate queries for each filter.
    """
    agg = Order.objects.filter(vendor=vendor).aggregate(
        total_revenue=Sum("total_amount", filter=Q(status="completed")),
        total_orders=Count("id", filter=Q(status="completed")),
        pending_orders=Count("id", filter=Q(status="pending")),
        confirmed_orders=Count("id", filter=Q(status="confirmed")),
        cancelled_orders=Count("id", filter=Q(status="cancelled")),
    )

    total_revenue = agg["total_revenue"] or 0
    total_orders = agg["total_orders"] or 0

    return {
        "total_revenue": float(total_revenue),
        "total_orders": total_orders,
        "pending_orders": agg["pending_orders"],
        "confirmed_orders": agg["confirmed_orders"],
        "cancelled_orders": agg["cancelled_orders"],
        "average_order_value": (
            round(float(total_revenue / total_orders), 2) if total_orders else 0
        ),
    }
