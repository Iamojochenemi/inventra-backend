from rest_framework import serializers
from .models import Category, Inventory, InventoryLog, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "vendor",
            "name",
            "is_active",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "is_active",
            "created_at",
        ]

        validators = []

    def validate(self, attrs):
        vendor = attrs["vendor"]
        name = attrs["name"]

        if Category.objects.filter(
            vendor=vendor,
            name=name
        ).exists():
            raise serializers.ValidationError(
                "Category with this name already exists for this vendor."
            )

        return attrs
    


class ProductSerializer(serializers.ModelSerializer):

    class Meta:
        model = Product
        fields = [
            "id",
            "vendor",
            "category",
            "name",
            "sku",
            "description",
            "price",
            "is_active",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]

        validators = []

    def validate(self, attrs):
        vendor = attrs["vendor"]
        category = attrs.get("category")

        # ensure category belongs to vendor
        if category and category.vendor != vendor:
            raise serializers.ValidationError(
                "Category does not belong to this vendor."
            )

        return attrs
    
class InventoryAdjustmentSerializer(serializers.Serializer):
    inventory_id = serializers.IntegerField()

    change_quantity = serializers.IntegerField(
        min_value=1
    )

    adjustment_type = serializers.ChoiceField(
        choices=InventoryLog.ADJUSTMENT_TYPES
    )

    reason = serializers.CharField(
        required=False,
        allow_blank=True
    )

    def validate_inventory_id(self, value):
        if not Inventory.objects.filter(id=value).exists():
            raise serializers.ValidationError(
                "Inventory record not found."
            )

        return value

    def validate(self, attrs):
        inventory = Inventory.objects.get(
            id=attrs["inventory_id"]
        )

        if (
            attrs["adjustment_type"] == "stock_out"
            and attrs["change_quantity"] > inventory.quantity
        ):
            raise serializers.ValidationError(
                "Insufficient stock available."
            )

        return attrs


class InventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source="product.name",
        read_only=True
    )

    branch_name = serializers.CharField(
        source="branch.name",
        read_only=True
    )

    class Meta:
        model = Inventory
        fields = [
            "id",
            "product",
            "product_name",
            "branch",
            "branch_name",
            "quantity",
            "updated_at",
        ]