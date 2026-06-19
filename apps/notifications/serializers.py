from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "type",
            "title",
            "message",
            "is_read",
            "created_at",
        ]


class MarkNotificationReadSerializer(serializers.Serializer):
    id = serializers.IntegerField()