from django.db.models import Count, Q

from apps.orders.models import Order


def get_customer_intelligence(vendor):
    """
    Aggregate customer metrics in a single grouping query.

    Groups orders by (customer_name, customer_phone) and uses conditional
    Count to bucket customers into repeat vs. one-time in one pass.
    """
    customers = Order.objects.filter(vendor=vendor).values(
        "customer_name",
        "customer_phone",
    ).annotate(
        total_orders=Count("id"),
    )

    total_customers = customers.count()
    repeat_customers = customers.filter(total_orders__gte=2).count()
    one_time_customers = customers.filter(total_orders=1).count()

    return {
        "total_customers": total_customers,
        "repeat_customers": repeat_customers,
        "one_time_customers": one_time_customers,
    }