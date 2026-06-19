from django.urls import path

from .views import (
    OrderListView,
    OrderDetailView,
    OrderCreateView,
    OrderStatusUpdateView,
)

urlpatterns = [
    path("", OrderListView.as_view(), name="order-list"),
    path("<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("create/", OrderCreateView.as_view(), name="order-create"),
    path("<int:pk>/status/", OrderStatusUpdateView.as_view(), name="order-status-update"),
]
