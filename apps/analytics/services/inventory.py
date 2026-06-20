from django.db.models import Sum, Count, F, Q

from apps.inventory.models import Inventory


def get_inventory_intelligence(vendor):
    """
    Aggregate inventory metrics in a single query.

    Computes total items, total stock value (quantity × price),
    low-stock alerts, and out-of-stock counts in one DB pass.
    """
    agg = Inventory.objects.filter(product__vendor=vendor).aggregate(
        total_items=Count("id"),
        total_stock_value=Sum(F("quantity") * F("product__price")),
        low_stock_items=Count(
            "id",
            filter=Q(quantity__gt=0) & Q(quantity__lte=F("low_stock_threshold")),
        ),
        out_of_stock=Count("id", filter=Q(quantity=0)),
    )

    return {
        "total_inventory_items": agg["total_items"],
        "total_stock_value": float(agg["total_stock_value"] or 0),
        "low_stock_items": agg["low_stock_items"],
        "out_of_stock": agg["out_of_stock"],
    }