# orders/admin.py

from django.contrib import admin
from django.db.models import Case, When, Value, IntegerField
from django.utils.html import format_html
from .models import Order, OrderItem, Wilaya, Commune
from django.contrib import messages
from django.core.exceptions import ValidationError
from products.models import ProductVariant

# @admin.register(Wilaya)
# class WilayaAdmin(admin.ModelAdmin):
#     list_display = ('id', 'name', 'domicile_price', 'bureau_price')
#     search_fields = ('name',)
#     ordering = ('name',)

# @admin.register(Commune)
# class CommuneAdmin(admin.ModelAdmin):
#     list_display = ('id', 'name', 'wilaya')
#     search_fields = ('name',)
#     ordering = ('name',)
#     list_filter = ('wilaya',)

#     def get_queryset(self, request):
#         return super().get_queryset(request).select_related('wilaya')



class OrderItemInline(admin.StackedInline):
    model = OrderItem
    extra = 1
    fields = (
        'product_variant',
        'quantity',
        'price',
        'get_product_name',
        'get_product_size',
        'get_product_color',
    )
    readonly_fields = ('price', 'get_product_name', 'get_product_size', 'get_product_color')

    def get_product_name(self, item_obj):
        return item_obj.product_variant.product.name if item_obj.product_variant else "-"
    get_product_name.short_description = 'Product'

    def get_product_size(self, item_obj):
        return item_obj.product_variant.size if item_obj.product_variant else "-"
    get_product_size.short_description = 'Size'

    def get_product_color(self, item_obj):
        return item_obj.product_variant.product.color if item_obj.product_variant else "-"
    get_product_color.short_description = 'Color'

    def has_add_permission(self, request, obj=None):
        return obj is None

    def has_delete_permission(self, request, obj=None):
        return obj is None

    def price_display(self, item_obj):
        return f"${item_obj.price:.2f}"
    price_display.short_description = 'Price'


@admin.action(description="Mark selected orders as Accepted")
def mark_as_accepted(modeladmin, request, queryset):
    pending_qs = queryset.filter(order_status__iexact="Pending")
    accepted_count = 0
    error_messages = []

    for order in pending_qs:
        # Try flipping to Accepted and saving
        order.order_status = "Accepted"
        try:
            # If you want to invoke your clean() stock‐check:
            order.full_clean()
            order.save()           # this will decrement stock
            order.update_total()   # recalc total AFTER stock has been decremented
            accepted_count += 1

        except ValidationError as e:
            # Pull out the specific order_status error (or all errors if you like)
            msg = e.error_dict.get("order_status") or e.messages
            # Normalize into a string
            if isinstance(msg, list):
                msg = "; ".join(str(m) for m in msg)
            elif hasattr(msg, "__iter__") and "order_status" in e.error_dict:
                msg = e.error_dict["order_status"][0]
            error_messages.append(f"Order #{order.pk}: {msg}")

    # Send a success banner if any orders were accepted
    if accepted_count:
        modeladmin.message_user(
            request,
            f"{accepted_count} order(s) marked as Accepted.",
            level=messages.SUCCESS
        )

    # Send one ERROR banner per problem order
    for err in error_messages:
        modeladmin.message_user(request, err, level=messages.ERROR)

@admin.action(description="Mark selected orders as Rejected")
def mark_as_rejected(modeladmin, request, queryset):
    # Only pick orders that are currently pending
    pending_qs = queryset.filter(order_status__iexact='Pending')

    rejected_count = 0
    for order in pending_qs:
        order.order_status = 'Rejected'
        order.save()            # ← triggers Order.save(), but no stock change on “Rejected”
        rejected_count += 1

    modeladmin.message_user(
        request,
        f"{rejected_count} order(s) marked as rejected."
    )

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'costumer_name',
        'costumer_phone',
        'order_date',
        'order_status_badge',
        'total_amount_formatted',
    )
    list_display_links = ('id','costumer_name')
    list_filter = ('order_status',)
    search_fields = ('costumer_name', 'costumer_phone')
    date_hierarchy = 'order_date'

    # Include both actions here:
    actions = [mark_as_accepted, mark_as_rejected]

    inlines = [OrderItemInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request).annotate(
            _status_order=Case(
                When(order_status__iexact='pending',  then=Value(0)),
                When(order_status__iexact='accepted', then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        return qs.order_by('_status_order', '-order_date')

    def get_readonly_fields(self, request, obj=None):
        if obj:
            status = obj.order_status.lower()
            # Once an order is accepted OR rejected, lock all fields (including status)
            if status in ('accepted', 'rejected'):
                return (
                    'costumer_name', 'costumer_phone', 'order_date',
                    'delivery_type', 'delivery_fees', 'wilaya', 'commune',
                    'order_status', 'total_amount'
                )


        # obj is None → Add form: only date & total are read‐only
        return ('order_date', 'total_amount')

    def order_status_badge(self, obj):
        COLOR = {
            'pending':  'badge bg-warning text-dark',
            'accepted': 'badge bg-success',
            'rejected': 'badge bg-danger',
        }
        css = COLOR.get(obj.order_status.lower(), 'badge bg-secondary')
        return format_html(f'<span class="{css}">{obj.order_status.capitalize()}</span>')
    order_status_badge.short_description = 'Status'
    order_status_badge.admin_order_field = 'order_status'

    def total_amount_formatted(self, obj):
        return f"{obj.total_amount:.2f}DA"
    total_amount_formatted.short_description = 'Total'
    total_amount_formatted.admin_order_field = 'total_amount'

    def get_actions(self, request):
        actions = super().get_actions(request) or {}
        status_filter = request.GET.get('order_status__exact', '').lower()

        # If we're already viewing accepted OR rejected orders, hide both bulk actions:
        if status_filter in ('accepted', 'rejected'):
            actions.pop('mark_as_accepted', None)
            actions.pop('mark_as_rejected', None)

        return actions
