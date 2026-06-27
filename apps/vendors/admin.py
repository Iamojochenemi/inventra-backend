from django.contrib import admin

from .models import Vendor, VendorStaff


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "is_active", "created_at")
    search_fields = ("name", "owner__email")
    list_filter = ("is_active",)


@admin.register(VendorStaff)
class VendorStaffAdmin(admin.ModelAdmin):
    list_display = ("id", "vendor", "user", "role", "branch", "created_at")
    search_fields = ("vendor__name", "user__email", "branch__name")
    list_filter = ("role", "vendor", "branch")
