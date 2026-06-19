from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema

from .models import Notification
from .serializers import (
    NotificationSerializer,
    MarkNotificationReadSerializer,
)


# -------------------------
# LIST NOTIFICATIONS
# -------------------------
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
    request=MarkNotificationReadSerializer,
    responses=NotificationSerializer,
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
    responses={"200": {"type": "object", "properties": {"message": {"type": "string"}}}},
)
class MarkAllNotificationsReadView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)

        return Response({"message": "All notifications marked as read"})