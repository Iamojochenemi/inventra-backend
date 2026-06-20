from django.db.models import Count, Q

from apps.deliveries.models import Delivery


def get_delivery_intelligence(vendor):
    """
    Aggregate delivery metrics in a single DB query using conditional Count.

    Returns counts for every delivery status plus the success rate
    in one pass instead of N separate .filter().count() calls.
    """
    agg = Delivery.objects.filter(order__vendor=vendor).aggregate(
        total=Count("id"),
        delivered=Count("id", filter=Q(status="delivered")),
        failed=Count("id", filter=Q(status="failed")),
        cancelled=Count("id", filter=Q(status="cancelled")),
        in_transit=Count("id", filter=Q(status="in_transit")),
        assigned=Count("id", filter=Q(status="assigned")),
        picked_up=Count("id", filter=Q(status="picked_up")),
        pending=Count("id", filter=Q(status="pending")),
    )

    total = agg["total"] or 0
    delivered = agg["delivered"] or 0

    return {
        "total_deliveries": total,
        "delivered": delivered,
        "failed": agg["failed"],
        "cancelled": agg["cancelled"],
        "in_transit": agg["in_transit"],
        "assigned": agg["assigned"],
        "picked_up": agg["picked_up"],
        "pending": agg["pending"],
        "success_rate": round((delivered / total) * 100, 2) if total else 0,
    }