"""
Tenant isolation mixin for multi-vendor data security.

Every view that accesses per-vendor data should inherit from
``TenantIsolationMixin`` and declare ``tenant_vendor_field`` so that
the user's vendor membership is automatically enforced at the queryset
level — returning **404 (Not Found)** instead of **403 (Forbidden)**
for cross-tenant resource IDs.
"""


class TenantIsolationMixin:
    """
    Enforces multi-tenant data isolation by scoping all querysets
    to the authenticated user's vendor staff memberships.

    Usage
    -----

    **Simple list / detail view (GenericAPIView subclass):**

    .. code-block:: python

        class OrderListView(TenantIsolationMixin, generics.ListAPIView):
            tenant_vendor_field = "vendor"
            # get_queryset() is auto-scoped; no manual filter needed.

    **View with custom ``get_queryset()`` — call ``self.scope_queryset()``:**

    .. code-block:: python

        class OrderListView(TenantIsolationMixin, generics.ListAPIView):
            tenant_vendor_field = "vendor"

            def get_queryset(self):
                qs = Order.objects.select_related("vendor", "branch")
                return self.scope_queryset(qs)

    **APIView with manual ``get_object_or_404``:**

    .. code-block:: python

        class InvoiceDetailView(TenantIsolationMixin, APIView):
            tenant_vendor_field = "order__vendor"

            def get(self, request, pk):
                invoice = get_object_or_404(
                    self.scope_queryset(Invoice.objects.all()),
                    pk=pk,
                )

    Rules
    -----
    * ``tenant_vendor_field`` is the relation path from the view's model
      to ``Vendor`` (e.g. ``"vendor"``, ``"order__vendor"``,
      ``"product__vendor"``).
    * The filter ``{field}__staff__user=self.request.user`` is applied,
      which resolves through the ``VendorStaff`` membership table.
    * Detail / action views automatically return **404** when a
      cross-tenant ID is supplied — preventing data enumeration.
    """

    #: Django relation path from this view's model to ``Vendor``.
    #: Examples: ``"vendor"``, ``"order__vendor"``, ``"product__vendor"``.
    tenant_vendor_field = None

    def scope_queryset(self, queryset):
        """
        Apply the tenant isolation filter to *queryset*.

        Call this from custom ``get_queryset()`` overrides, or use
        it directly with ``get_object_or_404()`` in action methods.
        """
        if not self.tenant_vendor_field:
            return queryset

        user = getattr(self.request, "user", None)
        if user is not None and user.is_authenticated:
            return queryset.filter(**{f"{self.tenant_vendor_field}__staff__user": user})
        return queryset

    def get_queryset(self):
        """
        Automatically scope the inherited ``get_queryset()`` result.

        Views that override ``get_queryset()`` should call
        ``self.scope_queryset()`` explicitly instead of relying on
        this default implementation.
        """
        qs = super().get_queryset()
        return self.scope_queryset(qs)
