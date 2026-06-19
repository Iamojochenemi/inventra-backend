from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Vendor, Branch, VendorSettings


@receiver(post_save, sender=Vendor)
def create_default_branch(sender, instance, created, **kwargs):
    if created:
        Branch.objects.create(
            vendor=instance,
            name="Main Branch"
        )


@receiver(post_save, sender=Vendor)
def create_default_settings(sender, instance, created, **kwargs):
    if created:
        VendorSettings.objects.get_or_create(vendor=instance)
