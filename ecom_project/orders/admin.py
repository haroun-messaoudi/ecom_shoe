from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, When, Value, IntegerField, Prefetch
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone
from django import forms

from .models import Order, OrderItem
from products.models import ProductVariant


# ----------------------------
# Inline: Order Items
# ----------------------------
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = (
        "product_variant",
        "quantity",
        "price",
        "get_product_name",
        "get_product_size",
        "get_product_color",
    )
    readonly_fields = ("price", "get_product_name", "get_product_size", "get_product_color")

    def get_readonly_fields(self, request, obj=None):
        ro = list(self.readonly_fields)
        if obj and obj.order_status in (
            Order.Status.ON_THE_WAY,
            Order.Status.DELIVERED,
            Order.Status.RETURNED_BY_CLIENT,
            Order.Status.RETURNED_BY_OWNER,
            Order.Status.CANCELLED,
        ):
            ro += ["product_variant", "quantity"]
        return ro

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("product_variant__product").only(
            "id",
            "order_id",
            "product_variant_id",
            "quantity",
            "price",
            "product_variant__size",
            "product_variant__stock",
            "product_variant__product__name",
            "product_variant__product__color",
        )

    def get_product_name(self, item_obj):
        return item_obj.product_variant.product.name if item_obj.product_variant else "-"
    get_product_name.short_description = "Product"

    def get_product_size(self, item_obj):
        return item_obj.product_variant.size if item_obj.product_variant else "-"
    get_product_size.short_description = "Size"

    def get_product_color(self, item_obj):
        return item_obj.product_variant.product.color if item_obj.product_variant else "-"
    get_product_color.short_description = "Color"

    def has_add_permission(self, request, obj=None):
        return obj is None

    def has_delete_permission(self, request, obj=None):
        return obj is None


# ----------------------------
# Custom Admin Form: restrict status choices
# ----------------------------
class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk and "order_status" in self.fields:
            current_status = self.instance.order_status

            allowed = {
                Order.Status.PENDING: [
                    Order.Status.PENDING,
                    Order.Status.CONFIRMED,
                    Order.Status.CANCELLED,
                ],
                Order.Status.CONFIRMED: [
                    Order.Status.CONFIRMED,
                    Order.Status.ON_THE_WAY,
                    Order.Status.CANCELLED,
                ],
                Order.Status.ON_THE_WAY: [
                    Order.Status.ON_THE_WAY,
                    Order.Status.DELIVERED,
                    Order.Status.RETURNED_BY_CLIENT,
                    Order.Status.RETURNED_BY_OWNER,
                ],
                Order.Status.DELIVERED: [Order.Status.DELIVERED],
                Order.Status.CANCELLED: [Order.Status.CANCELLED],
                Order.Status.RETURNED_BY_CLIENT: [Order.Status.RETURNED_BY_CLIENT],
                Order.Status.RETURNED_BY_OWNER: [Order.Status.RETURNED_BY_OWNER],
            }.get(current_status, [current_status])

            self.fields["order_status"].choices = [
                (code, label)
                for code, label in self.fields["order_status"].choices
                if code in allowed
            ]


# ----------------------------
# Main Admin: Order
# ----------------------------
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    inlines = [OrderItemInline]

    list_display = (
        "id",
        "costumer_name_link",
        "costumer_phone_link",
        "order_date",
        "order_status_badge",
        "total_amount_formatted",
    )
    list_display_links = ("id",)
    list_filter = ("order_status",)
    search_fields = ("costumer_name", "costumer_phone")
    date_hierarchy = "order_date"
    list_per_page = 25
    list_max_show_all = 200

    readonly_fields = (
        "order_date",
        "total_amount",
        "confirmed_at",
        "on_the_way_at",
        "delivered_at",
        "returned_at",
        "cancelled_at",
    )

    # ----------------------------
    # Lock fields when immutable
    # ----------------------------
    def get_readonly_fields(self, request, obj=None):
        ro = list(self.readonly_fields)
        if obj:
            if obj.order_status == Order.Status.ON_THE_WAY:
                # Lock customer & delivery info, but allow status changes
                ro += [
                    "costumer_name",
                    "costumer_phone",
                    "wilaya",
                    "commune",
                    "delivery_type",
                    "delivery_fees",
                ]
            elif obj.order_status in (
                Order.Status.DELIVERED,
                Order.Status.RETURNED_BY_CLIENT,
                Order.Status.RETURNED_BY_OWNER,
                Order.Status.CANCELLED,
            ):
                # Final states → lock everything including status
                ro += [
                    "costumer_name",
                    "costumer_phone",
                    "wilaya",
                    "commune",
                    "delivery_type",
                    "delivery_fees",
                    "order_status",
                ]
        return ro


    # ----------------------------
    # Query optimizations
    # ----------------------------
    def get_queryset(self, request):
        qs = super().get_queryset(request).annotate(
            _status_order=Case(
                When(order_status__iexact=Order.Status.PENDING, then=Value(0)),
                When(order_status__iexact=Order.Status.CONFIRMED, then=Value(1)),
                When(order_status__iexact=Order.Status.ON_THE_WAY, then=Value(2)),
                When(order_status__iexact=Order.Status.DELIVERED, then=Value(3)),
                default=Value(4),
                output_field=IntegerField(),
            )
        )
        url_name = request.resolver_match.url_name if request.resolver_match else None
        if url_name == "orders_order_changelist":
            return qs.order_by("_status_order", "-order_date")
        return qs.prefetch_related("items__product_variant", "items__product_variant__product") \
                 .order_by("_status_order", "-order_date")

    def get_object(self, request, object_id, from_field=None):
        queryset = self.get_queryset(request)
        model = queryset.model
        field = model._meta.pk if from_field is None else model._meta.get_field(from_field)
        try:
            object_id = field.to_python(object_id)
            return queryset.select_related().prefetch_related(
                "items__product_variant", "items__product_variant__product"
            ).get(**{field.name: object_id})
        except (model.DoesNotExist, ValidationError, ValueError):
            return None

    # ----------------------------
    # Helpers
    # ----------------------------
    def _change_url(self, obj):
        return reverse("admin:%s_%s_change" % (obj._meta.app_label, obj._meta.model_name), args=(obj.pk,))

    def costumer_name_link(self, obj):
        return format_html('<a href="{}">{}</a>', self._change_url(obj), obj.costumer_name)
    costumer_name_link.short_description = "Customer"

    def costumer_phone_link(self, obj):
        return format_html('<a href="{}">{}</a>', self._change_url(obj), obj.costumer_phone)
    costumer_phone_link.short_description = "Phone"

    def order_status_badge(self, obj):
        COLOR = {
            Order.Status.PENDING: "badge bg-warning text-dark",
            Order.Status.CONFIRMED: "badge bg-info text-dark",
            Order.Status.ON_THE_WAY: "badge bg-primary",
            Order.Status.DELIVERED: "badge bg-success",
            Order.Status.RETURNED_BY_CLIENT: "badge bg-danger",
            Order.Status.RETURNED_BY_OWNER: "badge bg-danger",
            Order.Status.CANCELLED: "badge bg-secondary",
        }
        css = COLOR.get(obj.order_status, "badge bg-dark")
        return format_html('<span class="{}">{}</span>', css, obj.get_order_status_display())
    order_status_badge.short_description = "Status"
    order_status_badge.admin_order_field = "order_status"

    def total_amount_formatted(self, obj):
        return f"{obj.total_amount:.2f} DA"
    total_amount_formatted.short_description = "Total"
    total_amount_formatted.admin_order_field = "total_amount"

    # ----------------------------
    # Save: enforce transitions
    # ----------------------------
    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)

        try:
            old = Order.objects.get(pk=obj.pk)
            old_status = old.order_status
        except Order.DoesNotExist:
            old_status = None

        new_status = obj.order_status
        valid_transitions = {
            Order.Status.PENDING: [Order.Status.CONFIRMED, Order.Status.CANCELLED],
            Order.Status.CONFIRMED: [Order.Status.ON_THE_WAY, Order.Status.CANCELLED],
            Order.Status.ON_THE_WAY: [Order.Status.DELIVERED, Order.Status.RETURNED_BY_CLIENT, Order.Status.RETURNED_BY_OWNER],
            Order.Status.DELIVERED: [],
            Order.Status.CANCELLED: [],
            Order.Status.RETURNED_BY_CLIENT: [],
            Order.Status.RETURNED_BY_OWNER: [],
        }

        # -----------------------------
        # Validate transition
        # -----------------------------
        if old_status != new_status and new_status not in valid_transitions.get(old_status, []):
            self.message_user(
                request,
                f"❌ Invalid transition: {old_status} → {new_status}",
                level=messages.ERROR,
            )
            return

        # -----------------------------
        # Stock check for Confirm / On the Way
        # -----------------------------
        if old_status != new_status and new_status in [Order.Status.CONFIRMED, Order.Status.ON_THE_WAY]:
            items = obj.items.select_related("product_variant")
            for it in items:
                pv = it.product_variant
                if pv and pv.stock < it.quantity:
                    self.message_user(
                        request,
                        f"❌ Not enough stock for {pv} (required {it.quantity}, available {pv.stock}). "
                        f"Order #{obj.pk} cannot be set to {new_status}.",
                        level=messages.ERROR,
                    )
                    return  # cancel save

        # -----------------------------
        # Set timestamps
        # -----------------------------
        now = timezone.now()
        if new_status == Order.Status.CONFIRMED and not obj.confirmed_at:
            obj.confirmed_at = now
        elif new_status == Order.Status.ON_THE_WAY and not obj.on_the_way_at:
            obj.on_the_way_at = now
        elif new_status == Order.Status.DELIVERED and not obj.delivered_at:
            obj.delivered_at = now
        elif new_status in (Order.Status.RETURNED_BY_CLIENT, Order.Status.RETURNED_BY_OWNER) and not obj.returned_at:
            obj.returned_at = now
        elif new_status == Order.Status.CANCELLED and not obj.cancelled_at:
            obj.cancelled_at = now

        super().save_model(request, obj, form, change)

    # ----------------------------
    # Actions
    # ----------------------------
    actions = [
        "mark_as_confirmed",
        "mark_as_on_the_way",
        "mark_as_delivered",
        "mark_as_cancelled",
        "mark_as_returned_client",
        "mark_as_returned_owner",
    ]

    # ------------------------
    # STATUS TRANSITION RULES
    # ------------------------

    def mark_as_confirmed(self, request, queryset):
        success = 0
        queryset = queryset.prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.select_related("product_variant"))
        )
        for order in queryset:
            try:
                with transaction.atomic():
                    if order.order_status != Order.Status.PENDING:
                        self.message_user(
                            request,
                            f"❌ Order #{order.pk} cannot be confirmed (current status: {order.order_status}). "
                            "Only Pending orders can be confirmed.",
                            level=messages.ERROR,
                        )
                        continue
                    for it in order.items.all():
                        pv = it.product_variant
                        if pv and pv.stock < it.quantity:
                            raise ValidationError(
                                f"❌ Order #{order.pk}: Not enough stock for {pv}."
                            )
                    order.order_status = Order.Status.CONFIRMED
                    order.confirmed_at = timezone.now()
                    order.save()
                    success += 1
            except ValidationError as e:
                self.message_user(request, str(e), level=messages.ERROR)
        if success:
            self.message_user(request, f"✅ {success} order(s) marked as Confirmed.", level=messages.SUCCESS)

    def mark_as_on_the_way(self, request, queryset):
        success = 0
        queryset = queryset.prefetch_related(
            Prefetch("items", queryset=OrderItem.objects.select_related("product_variant"))
        )
        for order in queryset:
            try:
                with transaction.atomic():
                    if order.order_status != Order.Status.CONFIRMED:
                        self.message_user(
                            request,
                            f"❌ Order #{order.pk} cannot be set to On The Way (current status: {order.order_status}). "
                            "Only Confirmed orders can be sent On The Way.",
                            level=messages.ERROR,
                        )
                        continue
                    variant_ids = list(
                        order.items.values_list("product_variant_id", flat=True).exclude(product_variant_id=None)
                    )
                    locked_variants = ProductVariant.objects.select_for_update().filter(pk__in=variant_ids)
                    variants_map = {v.pk: v for v in locked_variants}
                    for it in order.items.all():
                        v = variants_map.get(it.product_variant_id)
                        if v is None or v.stock < it.quantity:
                            raise ValidationError(
                                f"❌ Order #{order.pk}: Not enough stock for {it.product_variant}."
                            )
                    order.order_status = Order.Status.ON_THE_WAY
                    order.on_the_way_at = timezone.now()
                    order.save()
                    success += 1
            except ValidationError as e:
                self.message_user(request, str(e), level=messages.ERROR)
        if success:
            self.message_user(request, f"🚚 {success} order(s) marked as On The Way.", level=messages.SUCCESS)

    def mark_as_delivered(self, request, queryset):
        success = 0
        for order in queryset:
            if order.order_status != Order.Status.ON_THE_WAY:
                self.message_user(
                    request,
                    f"❌ Order #{order.pk} cannot be Delivered (current status: {order.order_status}). "
                    "Only On The Way orders can be Delivered.",
                    level=messages.ERROR,
                )
                continue
            order.order_status = Order.Status.DELIVERED
            order.delivered_at = timezone.now()
            order.save()
            success += 1
        if success:
            self.message_user(request, f"📦 {success} order(s) marked as Delivered.", level=messages.SUCCESS)

    def mark_as_cancelled(self, request, queryset):
        success = 0
        for order in queryset:
            if order.order_status not in (Order.Status.PENDING, Order.Status.CONFIRMED):
                self.message_user(
                    request,
                    f"❌ Order #{order.pk} cannot be Cancelled (current status: {order.order_status}). "
                    "Only Pending or Confirmed orders can be Cancelled.",
                    level=messages.ERROR,
                )
                continue
            order.order_status = Order.Status.CANCELLED
            order.cancelled_at = timezone.now()
            order.save()
            success += 1
        if success:
            self.message_user(request, f"⚠️ {success} order(s) marked as Cancelled.", level=messages.SUCCESS)

    def mark_as_returned_client(self, request, queryset):
        success = 0
        for order in queryset:
            if order.order_status != Order.Status.ON_THE_WAY:
                self.message_user(
                    request,
                    f"❌ Order #{order.pk} cannot be Returned by Client (current status: {order.order_status}). "
                    "Only On The Way orders can be Returned by Client.",
                    level=messages.ERROR,
                )
                continue
            order.order_status = Order.Status.RETURNED_BY_CLIENT
            order.returned_at = timezone.now()
            order.save()
            success += 1
        if success:
            self.message_user(request, f"↩️ {success} order(s) marked as Returned by Client.", level=messages.SUCCESS)

    def mark_as_returned_owner(self, request, queryset):
        success = 0
        for order in queryset:
            if order.order_status != Order.Status.ON_THE_WAY:
                self.message_user(
                    request,
                    f"❌ Order #{order.pk} cannot be Returned by Owner (current status: {order.order_status}). "
                    "Only On The Way orders can be Returned by Owner.",
                    level=messages.ERROR,
                )
                continue
            order.order_status = Order.Status.RETURNED_BY_OWNER
            order.returned_at = timezone.now()
            order.save()
            success += 1
        if success:
            self.message_user(request, f"↩️ {success} order(s) marked as Returned by Owner.", level=messages.SUCCESS)
