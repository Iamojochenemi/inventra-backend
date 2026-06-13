from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)

    role = models.CharField(
        max_length=20,
        choices=[
            ("admin", "Admin"),
            ("manager", "Manager"),
            ("staff", "Staff"),
            ("vendor", "Vendor"),
        ],
        default="vendor",
    )

    phone_number = models.CharField(max_length=20, blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email