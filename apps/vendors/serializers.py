from rest_framework import serializers

from .models import Branch, Vendor, VendorInvitation, VendorSettings, VendorStaff


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ["id", "name", "description", "is_active", "created_at"]
        read_only_fields = ["id", "is_active", "created_at"]

    def create(self, validated_data):
        request = self.context["request"]

        # create vendor
        vendor = Vendor.objects.create(owner=request.user, **validated_data)

        # get auto-created Main Branch
        main_branch = vendor.branches.filter(name="Main Branch").first()

        if not main_branch:
            raise serializers.ValidationError(
                "Main Branch was not created automatically."
            )

        # create owner membership
        VendorStaff.objects.create(
            vendor=vendor, branch=main_branch, user=request.user, role="owner"
        )

        return vendor


class VendorStaffSerializer(serializers.ModelSerializer):

    role = serializers.ChoiceField(
        choices=[
            ("manager", "Manager"),
            ("inventory", "Inventory Staff"),
            ("dispatcher", "Dispatcher"),
            ("rider", "Rider"),
        ]
    )

    class Meta:
        model = VendorStaff
        fields = ["id", "vendor", "branch", "user", "role", "created_at"]
        read_only_fields = ["id", "created_at"]
        validators = []

    def validate(self, attrs):
        vendor = attrs["vendor"]
        user = attrs["user"]
        branch = attrs.get("branch")

        # prevent duplicate membership
        if VendorStaff.objects.filter(vendor=vendor, user=user).exists():
            raise serializers.ValidationError("User already belongs to this vendor.")

        # ensure branch belongs to vendor
        if branch and branch.vendor != vendor:
            raise serializers.ValidationError("Branch does not belong to this vendor.")

        return attrs

    def create(self, validated_data):
        vendor = validated_data["vendor"]
        user = validated_data["user"]
        role = validated_data["role"]
        branch = validated_data.get("branch")

        # auto-assign Main Branch if none provided
        if not branch:
            branch = vendor.branches.filter(name="Main Branch").first()

        if not branch:
            raise serializers.ValidationError(
                "Vendor must have a Main Branch before adding staff."
            )

        return VendorStaff.objects.create(
            vendor=vendor, branch=branch, user=user, role=role
        )


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "vendor", "name", "address", "is_active", "created_at"]

        read_only_fields = ["id", "is_active", "created_at"]

    def validate(self, attrs):
        vendor = attrs["vendor"]
        name = attrs["name"]

        # prevent duplicate branch names per vendor
        if Branch.objects.filter(vendor=vendor, name=name).exists():
            raise serializers.ValidationError(
                "Branch with this name already exists for this vendor."
            )

        return attrs


class VendorInvitationCreateSerializer(serializers.Serializer):
    vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all())
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=[c for c in VendorStaff.ROLE_CHOICES if c[0] != "owner"]
    )


class VendorInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorInvitation
        fields = [
            "id",
            "vendor",
            "email",
            "role",
            "status",
            "created_at",
            "expires_at",
            "accepted_at",
        ]
        read_only_fields = fields


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)


class RejectInvitationSerializer(serializers.Serializer):
    token = serializers.CharField()


class VendorSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorSettings
        fields = [
            "business_registration_number",
            "tax_id",
            "currency",
            "enable_email_notifications",
            "enable_inventory_alerts",
            "enable_order_notifications",
            "enable_delivery_updates",
            "auto_process_payments",
            "payment_settlement_days",
            "allow_orders_when_low_stock",
            "auto_assign_deliveries",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class ResendInvitationSerializer(serializers.Serializer):
    pass
