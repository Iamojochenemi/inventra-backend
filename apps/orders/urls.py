from django.urls import path

from .views import (
    OrderCreateView,
    OrderStatusUpdateView,
)

urlpatterns = [
    path(
        "create/",
        OrderCreateView.as_view(),
        name="order-create"
    ),

    path(
        "<int:pk>/status/",
        OrderStatusUpdateView.as_view(),
        name="order-status-update"
    ),
]