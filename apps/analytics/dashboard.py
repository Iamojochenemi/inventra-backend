from django.core.cache import cache

from apps.analytics.services.customer import get_customer_intelligence
from apps.analytics.services.delivery import get_delivery_intelligence
from apps.analytics.services.inventory import get_inventory_intelligence
from apps.analytics.services.profit import get_profit_loss
from apps.analytics.services.revenue import get_revenue_intelligence


def get_vendor_dashboard(vendor):
    """
    Build the vendor analytics dashboard data.

    Each intelligence function now executes a single aggregate query,
    so the full dashboard is built from exactly 5 DB hits:
    1 order query (revenue), 1 order query (profit),
    1 order query (customer), 1 delivery query, 1 inventory query.

    Results are cached for 5 minutes to absorb burst traffic.
    """
    cache_key = f"vendor_dashboard_{vendor.id}"

    cached_data = cache.get(cache_key)
    if cached_data is not None:
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
