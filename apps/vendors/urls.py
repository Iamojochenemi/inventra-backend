from django.urls import path

from .views import (
    VendorCreateView,
    VendorStaffCreateView,
    BranchCreateView
)

urlpatterns = [
    path(
        "create/",
        VendorCreateView.as_view(),
        name="vendor-create"
    ),

    path(
        "staff/create/",
        VendorStaffCreateView.as_view(),
        name="vendor-staff-create"
    ),

    path(
        "branches/create/",
        BranchCreateView.as_view(),
        name="branch-create"
    ),
]