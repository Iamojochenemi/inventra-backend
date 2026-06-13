from django.db.models import Count, Avg
from apps.deliveries.models import Delivery


def get_delivery_intelligence(vendor):
    deliveries = Delivery.objects.filter(order__vendor=vendor)

    total = deliveries.count()

    if total == 0:
        return {
            "total_deliveries": 0,
            "delivered": 0,
            "failed": 0,
            "success_rate": 0,
        }

    delivered = deliveries.filter(status="delivered").count()
    failed = deliveries.filter(status="failed").count()

    success_rate = (delivered / total) * 100

    return {
        "total_deliveries": total,
        "delivered": delivered,
        "failed": failed,
        "success_rate": round(success_rate, 2),
    }