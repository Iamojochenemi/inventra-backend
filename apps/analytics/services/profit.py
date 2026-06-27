from django.db.models import F, Sum

from apps.orders.models import Order


def get_profit_loss(vendor):
    """
    Compute profit & loss in a single aggregate query.

    Revenue and COGS (cost of goods sold) are computed from completed orders
    using a single Sum with F-expression to multiply quantity × unit price
    across the OrderItem join.
    """
    agg = Order.objects.filter(
        vendor=vendor,
        status="completed",
    ).aggregate(
        revenue=Sum("total_amount"),
        cogs=Sum(F("items__quantity") * F("items__product__price")),
    )

    revenue = float(agg["revenue"] or 0)
    cogs = float(agg["cogs"] or 0)

    return {
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": round(revenue - cogs, 2),
    }
