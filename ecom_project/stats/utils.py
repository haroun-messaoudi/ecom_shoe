from django.db.models import Sum, Count, F, Q, FloatField
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from orders.models import Order
from products.models import Product, ProductVariant, Category

# ----------------------------
# Common Base QuerySets
# ----------------------------
ACCEPTED_ORDERS = Order.objects.filter(order_status="Accepted")

# ----------------------------
# Revenue & Orders Stats
# ----------------------------

def total_revenue():
    return ACCEPTED_ORDERS.aggregate(total=Sum("total_amount"))["total"] or 0

def orders_count():
    return Order.objects.count()

def orders_by_status():
    return Order.objects.values("order_status").annotate(count=Count("id"))

def orders_summary():
    agg = Order.objects.aggregate(
        total=Count("id"),
        accepted=Count("id", filter=Q(order_status="Accepted")),
    )
    by_status = Order.objects.values("order_status").annotate(count=Count("id"))
    return {**agg, "by_status": by_status}

def revenue_by_category():
    return Category.objects.annotate(
        revenue=Sum(
            F("products__sold") * F("products__price"),
            output_field=FloatField()
        )
    ).order_by("-revenue")

# ----------------------------
# Top / Low Stock Products
# ----------------------------

def top_selling_products(limit=10):
    return Product.objects.only("id", "name", "sold").order_by("-sold")[:limit]

def low_stock_products(threshold=5):
    return ProductVariant.objects.filter(stock__lte=threshold) \
        .select_related("product").order_by("stock")

# ----------------------------
# Time-based Revenue
# ----------------------------

def daily_revenue():
    return ACCEPTED_ORDERS.annotate(day=TruncDay("order_date")) \
        .values("day").annotate(total=Sum("total_amount")).order_by("day")

def weekly_revenue():
    return ACCEPTED_ORDERS.annotate(week=TruncWeek("order_date")) \
        .values("week").annotate(total=Sum("total_amount")).order_by("week")

def monthly_revenue():
    return ACCEPTED_ORDERS.annotate(month=TruncMonth("order_date")) \
        .values("month").annotate(total=Sum("total_amount")).order_by("month")

# ----------------------------
# Time-based Orders Count
# ----------------------------

def daily_orders():
    return ACCEPTED_ORDERS.annotate(day=TruncDay("order_date")) \
        .values("day").annotate(count=Count("id")).order_by("day")

def weekly_orders():
    return ACCEPTED_ORDERS.annotate(week=TruncWeek("order_date")) \
        .values("week").annotate(count=Count("id")).order_by("week")

def monthly_orders():
    return ACCEPTED_ORDERS.annotate(month=TruncMonth("order_date")) \
        .values("month").annotate(count=Count("id")).order_by("month")

# ----------------------------
# Conversion Rates
# ----------------------------

def conversion_overall():
    agg = Order.objects.aggregate(
        total=Count("id"),
        accepted=Count("id", filter=Q(order_status="Accepted")),
    )
    return round((agg["accepted"] / agg["total"] * 100), 2) if agg["total"] else 0

def conversion_per_wilaya():
    qs = Order.objects.values("wilaya").annotate(
        total=Count("id"),
        accepted=Count("id", filter=Q(order_status="Accepted"))
    )
    return [
        {
            "wilaya": row["wilaya"],
            "conversion": round((row["accepted"] / row["total"] * 100), 2) if row["total"] else 0,
            "total_orders": row["total"],
            "accepted_orders": row["accepted"],
        }
        for row in qs.order_by("-accepted")
    ]

# ----------------------------
# Products & Categories Stats
# ----------------------------

def best_selling_products(limit=10):
    return Product.objects.only("id", "name", "sold").order_by("-sold")[:limit]

def best_categories():
    return Category.objects.annotate(
        total_sold=Sum("products__sold")
    ).order_by("-total_sold")

# ----------------------------
# Monthly Best Sellers
# ----------------------------

def monthly_best_selling_products():
    monthly_orders_qs = ACCEPTED_ORDERS.annotate(month=TruncMonth("order_date")) \
        .values("month", "items__product_variant__product__id", "items__product_variant__product__name") \
        .annotate(total_sold=Sum("items__quantity")) \
        .order_by("month", "-total_sold")

    results = {}
    for entry in monthly_orders_qs:
        month = entry["month"]
        if month not in results:  # first (best) product per month
            results[month] = {
                "product_name": entry["items__product_variant__product__name"],
                "sold": entry["total_sold"],
            }
    return results

def monthly_best_categories():
    monthly_orders_qs = ACCEPTED_ORDERS.annotate(month=TruncMonth("order_date")) \
        .values("month", "items__product_variant__product__category__id", "items__product_variant__product__category__name") \
        .annotate(total_sold=Sum("items__quantity")) \
        .order_by("month", "-total_sold")

    results = {}
    for entry in monthly_orders_qs:
        month = entry["month"]
        if month not in results:  # first (best) category per month
            results[month] = {
                "category_name": entry["items__product_variant__product__category__name"],
                "sold": entry["total_sold"],
            }
    return results

# ----------------------------
# Delivery Fees Stats
# ----------------------------

def total_delivery_fees():
    return ACCEPTED_ORDERS.aggregate(total_fees=Sum("delivery_fees"))["total_fees"] or 0

# ----------------------------
# Insights for Owner
# ----------------------------

def revenue_trend_insight():
    monthly = list(monthly_revenue())
    if len(monthly) < 2:
        return "Not enough data to generate trend insights."
    last, prev = monthly[-1]["total"] or 0, monthly[-2]["total"] or 0
    if last > prev:
        return f"📈 Revenue increased by {round((last - prev) / prev * 100, 2) if prev else 0}% compared to previous month."
    elif last < prev:
        return f"📉 Revenue decreased by {round((prev - last) / prev * 100, 2) if prev else 0}% compared to previous month."
    return "Revenue stayed stable compared to previous month."

def orders_trend_insight():
    monthly = list(monthly_orders())
    if len(monthly) < 2:
        return "Not enough data to generate trend insights."
    last, prev = monthly[-1]["count"] or 0, monthly[-2]["count"] or 0
    if last > prev:
        return f"📈 Orders increased by {round((last - prev) / prev * 100, 2) if prev else 0}% compared to previous month."
    elif last < prev:
        return f"📉 Orders decreased by {round((prev - last) / prev * 100, 2) if prev else 0}% compared to previous month."
    return "Orders stayed stable compared to previous month."

# ----------------------------
# Stock & Restock Insights
# ----------------------------

def stock_warnings():
    empty_stock = ProductVariant.objects.filter(stock=0).select_related("product")
    low_stock = ProductVariant.objects.filter(stock__lte=5, stock__gt=0).select_related("product")

    warnings = [
        f"⚠️ '{p.product.name}' (Size: {p.size}) is out of stock!" for p in empty_stock
    ]
    warnings += [
        f"⚠️ '{p.product.name}' (Size: {p.size}) has low stock ({p.stock} left)" for p in low_stock
    ]
    return warnings

def restock_suggestions(limit=5):
    low_stock_top = ProductVariant.objects.filter(stock__lte=5) \
        .select_related("product").order_by("-product__sold")[:limit]
    return [
        f"🔄 Consider restocking '{p.product.name}' (Size: {p.size}), sold {p.product.sold} units"
        for p in low_stock_top
    ]

# ----------------------------
# Additional Actionable Insights
# ----------------------------

def average_order_value():
    total = total_revenue()
    count = ACCEPTED_ORDERS.count()
    return round(total / count, 2) if count else 0

def high_performing_wilayas(limit=5):
    qs = ACCEPTED_ORDERS.values("wilaya").annotate(total_orders=Count("id")) \
        .order_by("-total_orders")[:limit]
    return list(qs)

def slow_moving_products(limit=10):
    return Product.objects.only("id", "name", "sold") \
        .annotate(total_sold=F("sold")).order_by("total_sold")[:limit]

def delivery_performance():
    total_orders = ACCEPTED_ORDERS.count()
    total_fees = ACCEPTED_ORDERS.aggregate(total=Sum("delivery_fees"))["total"] or 0
    avg_fee = round(total_fees / total_orders, 2) if total_orders else 0

    top_delivery_type_qs = ACCEPTED_ORDERS.values("delivery_type") \
        .annotate(count=Count("id")).order_by("-count").first()
    top_delivery_type = top_delivery_type_qs["delivery_type"] if top_delivery_type_qs else None

    return {"average_fee": avg_fee, "top_delivery_type": top_delivery_type}

def fast_selling_low_stock(limit=5):
    low_stock_top = ProductVariant.objects.filter(stock__lte=5) \
        .select_related("product").order_by("-product__sold")[:limit]
    return [
        f"🔥 '{p.product.name}' (Size: {p.size}) sold {p.product.sold}, only {p.stock} left"
        for p in low_stock_top
    ]
