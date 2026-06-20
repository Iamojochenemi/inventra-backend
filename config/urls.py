from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


@extend_schema(tags=["Auth"], summary="Obtain JWT token pair")
class _TokenObtainPairView(TokenObtainPairView):
    pass


@extend_schema(tags=["Auth"], summary="Refresh JWT access token")
class _TokenRefreshView(TokenRefreshView):
    pass


urlpatterns = [
    path('admin/', admin.site.urls),
    # schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),

   path(
    "api/swagger/",
    SpectacularSwaggerView.as_view(url_name="schema"),
    name="swagger-ui"
),
    # redoc UI (optional)
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),


    path("api/accounts/", include("apps.accounts.urls")),
    path("api/vendors/", include("apps.vendors.urls")),

    path("api/inventory/", include("apps.inventory.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/deliveries/", include("apps.deliveries.urls")),

    path("api/auth/token/", _TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", _TokenRefreshView.as_view(), name="token_refresh"),

    path("api-auth/", include("rest_framework.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
