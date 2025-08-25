from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from orders.models import Order
from products.models import Product, ProductVariant, Category

# ----------------------------
# Revenue & Orders Stats
# ----------------------------

def total_revenue():
    return Order.objects.filter(order_status='Accepted').aggregate(
        total=Sum('total_amount')
    )['total'] or 0

def orders_count():
    return Order.objects.all().count()  # Returns only accepted orders

def orders_by_status():
    return Order.objects.values('order_status').annotate(count=Count('id'))

# Alternative: If you want both accepted and total counts
def orders_summary():
    total = Order.objects.count()
    accepted = Order.objects.filter(order_status='Accepted').count()
    by_status = Order.objects.values('order_status').annotate(count=Count('id'))
    return {
        'total': total,
        'accepted': accepted,
        'by_status': by_status
    }

def revenue_by_category():
    return Category.objects.annotate(
        revenue=Sum(F('products__sold') * F('products__price'))
    ).order_by('-revenue')

# ----------------------------
# Top / Low Stock Products
# ----------------------------

def top_selling_products(limit=10):
    return Product.objects.order_by('-sold')[:limit]

def low_stock_products(threshold=5):
    return ProductVariant.objects.filter(stock__lte=threshold).order_by('stock')

# ----------------------------
# Time-based Revenue
# ----------------------------

def daily_revenue():
    orders = Order.objects.filter(order_status='Accepted')
    return orders.annotate(day=TruncDay('order_date')) \
                 .values('day') \
                 .annotate(total=Sum('total_amount')) \
                 .order_by('day')

def weekly_revenue():
    orders = Order.objects.filter(order_status='Accepted')
    return orders.annotate(week=TruncWeek('order_date')) \
                 .values('week') \
                 .annotate(total=Sum('total_amount')) \
                 .order_by('week')

def monthly_revenue():
    orders = Order.objects.filter(order_status='Accepted')
    return orders.annotate(month=TruncMonth('order_date')) \
                 .values('month') \
                 .annotate(total=Sum('total_amount')) \
                 .order_by('month')

# ----------------------------
# Time-based Orders Count
# ----------------------------

def daily_orders():
    orders = Order.objects.filter(order_status='Accepted')
    return orders.annotate(day=TruncDay('order_date')) \
                 .values('day') \
                 .annotate(count=Count('id')) \
                 .order_by('day')

def weekly_orders():
    orders = Order.objects.filter(order_status='Accepted')
    return orders.annotate(week=TruncWeek('order_date')) \
                 .values('week') \
                 .annotate(count=Count('id')) \
                 .order_by('week')

def monthly_orders():
    orders = Order.objects.filter(order_status='Accepted')
    return orders.annotate(month=TruncMonth('order_date')) \
                 .values('month') \
                 .annotate(count=Count('id')) \
                 .order_by('month')

# ----------------------------
# Conversion Rates
# ----------------------------

def conversion_overall():
    total = Order.objects.count()
    accepted = Order.objects.filter(order_status='Accepted').count()
    return round((accepted / total * 100), 2) if total else 0

def conversion_per_wilaya():
    wilayas = Order.objects.values('wilaya').distinct()
    result = []
    for w in wilayas:
        total = Order.objects.filter(wilaya=w['wilaya']).count()
        accepted = Order.objects.filter(wilaya=w['wilaya'], order_status='Accepted').count()
        conversion = round((accepted / total * 100), 2) if total else 0
        result.append({
            'wilaya': w['wilaya'],
            'conversion': conversion,
            'total_orders': total,
            'accepted_orders': accepted
        })
    return sorted(result, key=lambda x: x['conversion'], reverse=True)

# ----------------------------
# Products & Categories Stats
# ----------------------------

def best_selling_products(limit=10):
    return Product.objects.order_by('-sold')[:limit]

def best_categories():
    return Category.objects.annotate(
        total_sold=Sum('products__sold')
    ).order_by('-total_sold')

# ----------------------------
# Monthly Best Sellers
# ----------------------------

def monthly_best_selling_products(limit=1):
    monthly_orders_qs = Order.objects.filter(order_status='Accepted') \
        .annotate(month=TruncMonth('order_date')) \
        .values('month', 'items__product_variant__product__id', 'items__product_variant__product__name') \
        .annotate(total_sold=Sum('items__quantity')) \
        .order_by('month', '-total_sold')

    results = {}
    for entry in monthly_orders_qs:
        month = entry['month']
        if month not in results:
            results[month] = {
                'product_name': entry['items__product_variant__product__name'],
                'sold': entry['total_sold']
            }
    return results

def monthly_best_categories(limit=1):
    monthly_orders_qs = Order.objects.filter(order_status='Accepted') \
        .annotate(month=TruncMonth('order_date')) \
        .values('month', 'items__product_variant__product__category__id', 'items__product_variant__product__category__name') \
        .annotate(total_sold=Sum('items__quantity')) \
        .order_by('month', '-total_sold')

    results = {}
    for entry in monthly_orders_qs:
        month = entry['month']
        if month not in results:
            results[month] = {
                'category_name': entry['items__product_variant__product__category__name'],
                'sold': entry['total_sold']
            }
    return results

# ----------------------------
# Delivery Fees Stats
# ----------------------------

def total_delivery_fees():
    return Order.objects.filter(order_status='Accepted').aggregate(
        total_fees=Sum('delivery_fees')
    )['total_fees'] or 0

# ----------------------------
# Insights for Owner
# ----------------------------

def revenue_trend_insight():
    monthly = list(monthly_revenue())
    if len(monthly) < 2:
        return "Not enough data to generate trend insights."
    last_month = monthly[-1]['total'] or 0
    prev_month = monthly[-2]['total'] or 0
    if last_month > prev_month:
        return f"📈 Revenue increased by {round((last_month-prev_month)/prev_month*100,2) if prev_month else 0}% compared to previous month."
    elif last_month < prev_month:
        return f"📉 Revenue decreased by {round((prev_month-last_month)/prev_month*100,2) if prev_month else 0}% compared to previous month."
    else:
        return "Revenue stayed stable compared to previous month."

def orders_trend_insight():
    monthly = list(monthly_orders())
    if len(monthly) < 2:
        return "Not enough data to generate trend insights."
    last_month = monthly[-1]['count'] or 0
    prev_month = monthly[-2]['count'] or 0
    if last_month > prev_month:
        return f"📈 Orders increased by {round((last_month-prev_month)/prev_month*100,2) if prev_month else 0}% compared to previous month."
    elif last_month < prev_month:
        return f"📉 Orders decreased by {round((prev_month-last_month)/prev_month*100,2) if prev_month else 0}% compared to previous month."
    else:
        return "Orders stayed stable compared to previous month."

# ----------------------------
# Stock & Restock Insights
# ----------------------------

def stock_warnings():
    empty_stock = ProductVariant.objects.filter(stock=0)
    low_stock = ProductVariant.objects.filter(stock__lte=5, stock__gt=0)
    warnings = []
    for p in empty_stock:
        warnings.append(f"⚠️ '{p.product.name}' (Size: {p.size}) is out of stock!")
    for p in low_stock:
        warnings.append(f"⚠️ '{p.product.name}' (Size: {p.size}) has low stock ({p.stock} left)")
    return warnings

def restock_suggestions(limit=5):
    low_stock_top = ProductVariant.objects.filter(stock__lte=5).order_by('-product__sold')[:limit]
    suggestions = []
    for p in low_stock_top:
        suggestions.append(f"🔄 Consider restocking '{p.product.name}' (Size: {p.size}), sold {p.product.sold} units")
    return suggestions

# ----------------------------
# Additional Actionable Insights
# ----------------------------

def average_order_value():
    total = total_revenue()
    count = Order.objects.filter(order_status='Accepted').count()
    return round(total / count, 2) if count else 0

def high_performing_wilayas(limit=5):
    qs = Order.objects.filter(order_status='Accepted') \
        .values('wilaya') \
        .annotate(total_orders=Count('id')) \
        .order_by('-total_orders')[:limit]
    return list(qs)

def slow_moving_products(limit=10):
    return Product.objects.annotate(total_sold=F('sold')).order_by('total_sold')[:limit]

def delivery_performance():
    accepted_orders = Order.objects.filter(order_status='Accepted')
    total_orders = accepted_orders.count()
    total_fees = accepted_orders.aggregate(total=Sum('delivery_fees'))['total'] or 0
    avg_fee = round(total_fees / total_orders, 2) if total_orders else 0

    top_delivery_type_qs = accepted_orders.values('delivery_type') \
        .annotate(count=Count('id')).order_by('-count').first()
    top_delivery_type = top_delivery_type_qs['delivery_type'] if top_delivery_type_qs else None

    return {'average_fee': avg_fee, 'top_delivery_type': top_delivery_type}

def fast_selling_low_stock(limit=5):
    low_stock_top = ProductVariant.objects.filter(stock__lte=5).order_by('-product__sold')[:limit]
    return [
        f"🔥 '{p.product.name}' (Size: {p.size}) sold {p.product.sold}, only {p.stock} left"
        for p in low_stock_top
    ]
