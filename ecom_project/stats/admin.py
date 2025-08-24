from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from django.db.models import Sum, Count, F
from django.core.serializers.json import DjangoJSONEncoder
import json
from stats.utils import (
    total_revenue, orders_count, daily_revenue, weekly_revenue, monthly_revenue,
    daily_orders, weekly_orders, monthly_orders,
    conversion_overall, conversion_per_wilaya,
    best_categories, top_selling_products, low_stock_products,
    total_delivery_fees, revenue_trend_insight, orders_trend_insight,
    stock_warnings, restock_suggestions,
    monthly_best_selling_products, monthly_best_categories
)
from orders.models import Order
from products.models import Product

# Helper function to serialize data properly for charts
def serialize_chart_data(queryset):
    """Convert Django QuerySet to JSON-serializable format"""
    if not queryset:
        return []
    
    result = []
    for item in queryset:
        # Handle different possible field names
        date_field = None
        value_field = None
        
        # Find date field
        for field in ['day', 'week', 'month', 'date', 'order_date']:
            if field in item:
                date_field = item[field]
                break
        
        # Find value field
        for field in ['total', 'count', 'total_amount']:
            if field in item:
                value_field = item[field]
                break
        
        # Create standardized format
        if date_field is not None and value_field is not None:
            result.append({
                'date': date_field.isoformat() if hasattr(date_field, 'isoformat') else str(date_field),
                'value': float(value_field) if value_field else 0
            })
    
    return result

def stats_dashboard(request):
    orders_accepted = Order.objects.filter(order_status='Accepted')
    total_orders_count = orders_accepted.count()

    # Get chart data
    daily_rev = list(daily_revenue())
    weekly_rev = list(weekly_revenue())
    monthly_rev = list(monthly_revenue())
    daily_ord = list(daily_orders())
    weekly_ord = list(weekly_orders())
    monthly_ord = list(monthly_orders())
    
    # Debug: Print sample data to console
    print("Sample daily_revenue data:", daily_rev[:3] if daily_rev else "No data")
    print("Sample daily_orders data:", daily_ord[:3] if daily_ord else "No data")

    # Delivery performance
    delivery_perf = {
        'average_fee': orders_accepted.aggregate(
            avg_fee=Sum('delivery_fees') / Count('id')
        )['avg_fee'] if total_orders_count else 0,
        'top_delivery_type': orders_accepted.values('delivery_type')\
            .annotate(count=Count('id'))\
            .order_by('-count')\
            .first()['delivery_type'] if total_orders_count else 'N/A'
    }

    # Serialize chart data properly
    context = {
        # Basic stats
        'total_revenue': total_revenue(),
        'orders_count': list(orders_count()),
        'total_delivery_fees': total_delivery_fees(),
        'top_selling_products': list(top_selling_products()),
        'low_stock_products': list(low_stock_products()),
        
        # Chart data - serialized properly
        'daily_revenue': serialize_chart_data(daily_rev),
        'weekly_revenue': serialize_chart_data(weekly_rev),
        'monthly_revenue': serialize_chart_data(monthly_rev),
        'daily_orders': serialize_chart_data(daily_ord),
        'weekly_orders': serialize_chart_data(weekly_ord),
        'monthly_orders': serialize_chart_data(monthly_ord),
        
        # Other stats
        'conversion_overall': conversion_overall(),
        'conversion_per_wilaya': list(conversion_per_wilaya()),
        'best_categories': list(best_categories()),
        'revenue_trend_insight': revenue_trend_insight(),
        'orders_trend_insight': orders_trend_insight(),
        'stock_warnings': list(stock_warnings()),
        'restock_suggestions': list(restock_suggestions()),
        'orders_today_count': orders_count().filter(order_status='Accepted').aggregate(
            total=Sum('count')
        )['total'] or 0,

        # Enhanced stats
        'high_performing_wilayas': sorted(
            list(conversion_per_wilaya()), 
            key=lambda x: x['total_orders'], 
            reverse=True
        )[:10],
        'slow_moving_products': list(Product.objects.order_by('sold')[:10]),
        'delivery_performance': delivery_perf,
        'monthly_best_selling_products': monthly_best_selling_products(),
        'monthly_best_categories': monthly_best_categories(),
        'average_order_value': total_revenue() / total_orders_count if total_orders_count else 0,
        
        # Enhanced charts data for debugging
        'fast_selling_low_stock': [],  # Add this if you have the function
    }
    
    # Debug: Print context keys
    print("Context keys:", list(context.keys()))
    print("Daily revenue count:", len(context['daily_revenue']))
    print("Weekly revenue count:", len(context['weekly_revenue']))
    
    return render(request, "admin/stats_dashboard.html", context)

# Rest of your admin URL injection code remains the same
original_get_urls = admin.site.get_urls

def get_urls():
    urls = original_get_urls()
    custom_urls = [
        path('stats/dashboard/', admin.site.admin_view(stats_dashboard), name='stats-dashboard'),
    ]
    return custom_urls + urls

admin.site.get_urls = get_urls