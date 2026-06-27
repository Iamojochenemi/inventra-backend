from django.db import models


class Notification(models.Model):
    TYPE_CHOICES = (
        ("order", "Order"),
        ("delivery", "Delivery"),
        ("inventory", "Inventory"),
        ("system", "System"),
    )

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    title = models.CharField(max_length=255)
    message = models.TextField()

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type} - {self.title}"
