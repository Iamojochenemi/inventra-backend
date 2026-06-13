from django.db.models import Sum, F
from apps.orders.models import Order
from apps.inventory.models import Inventory


def get_profit_loss(vendor):
    orders = Order.objects.filter(vendor=vendor, status="completed")

    revenue = orders.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    # cost of goods sold (COGS)
    cogs = orders.exclude(items__isnull=True).aggregate(
        cost=Sum(F("items__quantity") * F("items__product__price"))
    )["cost"] or 0

    gross_profit = float(revenue) - float(cogs)

    return {
        "revenue": float(revenue),
        "cogs": float(cogs),
        "gross_profit": gross_profit
    }