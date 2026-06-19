from django.urls import path

from .views import (
    VendorListView,
    VendorCreateView,
    VendorStaffCreateView,
    VendorStaffListView,
    BranchCreateView,
    BranchListView,
    VendorSettingsView,
    InvitationCreateView,
    InvitationListView,
    AcceptInvitationView,
    RejectInvitationView,
    ResendInvitationView,
)

urlpatterns = [
    path("", VendorListView.as_view(), name="vendor-list"),
    path("create/", VendorCreateView.as_view(), name="vendor-create"),
    path("staff/create/", VendorStaffCreateView.as_view(), name="vendor-staff-create"),
    path("staff/", VendorStaffListView.as_view(), name="vendor-staff-list"),
    path("branches/create/", BranchCreateView.as_view(), name="branch-create"),
    path("branches/", BranchListView.as_view(), name="branch-list"),
    path("<int:vendor_id>/settings/", VendorSettingsView.as_view(), name="vendor-settings"),
    path("invitations/create/", InvitationCreateView.as_view(), name="invitation-create"),
    path("invitations/", InvitationListView.as_view(), name="invitation-list"),
    path("invitations/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
    path("invitations/reject/", RejectInvitationView.as_view(), name="invitation-reject"),
    path("invitations/<int:pk>/resend/", ResendInvitationView.as_view(), name="invitation-resend"),
]
