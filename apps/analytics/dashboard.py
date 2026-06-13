from django.core.cache import cache

from apps.analytics.services.customer import get_customer_intelligence
from apps.analytics.services.revenue import get_revenue_intelligence
from apps.analytics.services.inventory import get_inventory_intelligence
from apps.analytics.services.profit import get_profit_loss
from apps.analytics.services.delivery import get_delivery_intelligence


def get_vendor_dashboard(vendor):
    cache_key = f"vendor_dashboard_{vendor.id}"

    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    data = {
        "customer": get_customer_intelligence(vendor),
        "revenue": get_revenue_intelligence(vendor),
        "inventory": get_inventory_intelligence(vendor),
        "profit": get_profit_loss(vendor),
        "delivery": get_delivery_intelligence(vendor),
    }

    cache.set(cache_key, data, timeout=60 * 5)  # 5 minutes

    return data