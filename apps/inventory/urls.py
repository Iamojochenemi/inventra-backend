from django.urls import path

from .views import (
    CategoryCreateView,
    InventoryAdjustmentView,
    InventoryListView,
    ProductCreateView,
)

urlpatterns = [
    path("categories/create/", CategoryCreateView.as_view(), name="category-create"),
    path("products/create/", ProductCreateView.as_view(), name="product-create"),
    path("inventory/", InventoryListView.as_view(), name="inventory-list"),
    path(
        "inventory/adjust/", InventoryAdjustmentView.as_view(), name="inventory-adjust"
    ),
]
