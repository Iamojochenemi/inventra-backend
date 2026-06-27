from django.urls import path

from .views import VendorAnalyticsDashboardView

urlpatterns = [
    path(
        "dashboard/", VendorAnalyticsDashboardView.as_view(), name="analytics-dashboard"
    ),
]
