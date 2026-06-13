from django.db.models import Sum, F
from apps.inventory.models import Inventory


def get_inventory_intelligence(vendor):
    inventory = Inventory.objects.filter(product__vendor=vendor)

    total_items = inventory.count()

    total_stock_value = inventory.aggregate(
        value=Sum(F("quantity") * F("product__price"))
    )["value"] or 0

    return {
        "total_inventory_items": total_items,
        "total_stock_value": float(total_stock_value)
    }