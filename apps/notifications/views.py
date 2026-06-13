from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Notification
from .serializers import NotificationSerializer


# -------------------------
# LIST NOTIFICATIONS
# -------------------------
class NotificationListView(generics.ListAPIView):
    """
    Returns all notifications for the logged-in user.
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(
            user=self.request.user
        ).order_by("-created_at")


# -------------------------
# MARK SINGLE NOTIFICATION AS READ
# -------------------------
class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(
            Notification,
            id=pk,
            user=request.user
        )

        notification.is_read = True
        notification.save()

        return Response(
            {"message": "Notification marked as read"},
            status=status.HTTP_200_OK
        )


# -------------------------
# MARK ALL NOTIFICATIONS AS READ
# -------------------------
class MarkAllNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)

        return Response(
            {"message": "All notifications marked as read"},
            status=status.HTTP_200_OK
        )