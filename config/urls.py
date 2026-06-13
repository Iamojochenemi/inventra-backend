from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),

    path("api/accounts/", include("apps.accounts.urls")),
    path("api/vendors/", include("apps.vendors.urls")),

    path("api/inventory/", include("apps.inventory.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/analytics/", include("apps.analytics.urls")),

    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("api-auth/", include("rest_framework.urls")),
]