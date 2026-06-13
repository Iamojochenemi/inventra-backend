from django.contrib import admin

from apps.inventory.models import Inventory, Product

# Register your models here.
admin.site.register(Product)
admin.site.register(Inventory)