from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.vendors.services.vendor_service import get_user_vendors
from apps.analytics.dashboard import get_vendor_dashboard


@extend_schema(
    tags=["Analytics"],
    summary="Vendor analytics dashboard",
    description="Retrieve aggregated analytics data (revenue, inventory, customers, deliveries) for a vendor.",
    parameters=[
        OpenApiParameter(
            name="vendor_id",
            type=int,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Vendor ID to fetch analytics for",
        ),
    ],
    responses={
        200: OpenApiResponse(description="Analytics dashboard data"),
        400: OpenApiResponse(description="vendor_id is required"),
        403: OpenApiResponse(description="Invalid vendor_id or access denied"),
    },
)
class VendorAnalyticsDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vendor_id = request.query_params.get("vendor_id")

        if not vendor_id:
            return Response(
                {"detail": "vendor_id is required."},
                status=400,
            )

        vendor = get_user_vendors(request.user).filter(id=vendor_id).first()

        if not vendor:
            return Response(
                {"detail": "Invalid vendor_id or access denied."},
                status=403,
            )

        data = get_vendor_dashboard(vendor)
        return Response(data)
