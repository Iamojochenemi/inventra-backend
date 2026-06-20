from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import Notification
from .serializers import (
    NotificationSerializer,
    MarkNotificationReadSerializer,
)


# -------------------------
# LIST NOTIFICATIONS
# -------------------------
@extend_schema(
    tags=["Notifications"],
    summary="List notifications",
    description="Returns all notifications for the authenticated user, ordered by newest first.",
    responses={
        200: NotificationSerializer(many=True),
    },
)
class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(
            user=self.request.user
        ).order_by("-created_at")


# -------------------------
# MARK ONE AS READ (CLEAN GENERIC VIEW)
# -------------------------
@extend_schema(
    tags=["Notifications"],
    summary="Mark notification as read",
    description="Mark a single notification as read by providing its ID in the request body.",
    request=MarkNotificationReadSerializer,
    responses={
        200: NotificationSerializer,
        404: OpenApiResponse(description="Notification not found"),
    },
)
class MarkNotificationReadView(generics.GenericAPIView):
    serializer_class = MarkNotificationReadSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notification = get_object_or_404(
            Notification,
            id=serializer.validated_data["id"],
            user=request.user,
        )

        notification.is_read = True
        notification.save()

        return Response(NotificationSerializer(notification).data)


# -------------------------
# MARK ALL AS READ
# -------------------------
@extend_schema(
    tags=["Notifications"],
    summary="Mark all notifications as read",
    description="Mark all unread notifications for the authenticated user as read.",
    request=None,
    responses={
        200: {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
        },
    },
)
class MarkAllNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)

        return Response({"message": "All notifications marked as read"})