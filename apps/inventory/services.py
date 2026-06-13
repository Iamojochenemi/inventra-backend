from .models import Inventory


def initialize_product_inventory(product):
    """
    Create inventory records for all vendor branches
    when a new product is created.
    """

    branches = product.vendor.branches.all()

    inventory_records = [
        Inventory(
            product=product,
            branch=branch,
            quantity=0
        )
        for branch in branches
    ]

    Inventory.objects.bulk_create(inventory_records)