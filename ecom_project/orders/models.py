# orders/models.py

from decimal import Decimal
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from products.models import Product, ProductVariant
from django.core.exceptions import ValidationError
from django.db.models import Sum

class Wilaya(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)  # Added db_index
    domicile_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bureau_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    class Meta:
        ordering = ["name"]
        verbose_name = "Wilaya"
        verbose_name_plural = "Wilayas"

    def __str__(self):
        return self.name
    
class Commune(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)  # Added db_index
    wilaya = models.ForeignKey(Wilaya, related_name='communes', on_delete=models.CASCADE, db_index=True)  # Added db_index

    class Meta:
        unique_together = ["wilaya", "name"]
        ordering = ["name"]
        verbose_name = "Commune"
        verbose_name_plural = "Communes"

    def __str__(self):
        return self.name

from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from products.models import ProductVariant


class Order(models.Model):
    # -----------------------
    # Status Choices
    # -----------------------
    class Status(models.TextChoices):
        PENDING = "Pending", _("Pending")
        CONFIRMED = "Confirmed", _("Confirmed")
        ON_THE_WAY = "OnTheWay", _("On the Way")
        DELIVERED = "Delivered", _("Delivered")
        RETURNED_BY_CLIENT = "ReturnedByClient", _("Returned by Client")
        RETURNED_BY_OWNER = "ReturnedByOwner", _("Returned by Owner")
        CANCELLED = "Cancelled", _("Cancelled")
    class DeliveryType(models.TextChoices):
        HOME = "Home", _("Home Delivery")
        BUREAU = "Bureau", _("Bureau Delivery")

    # -----------------------
    # Basic fields
    # -----------------------
    costumer_name = models.CharField(max_length=255)
    costumer_phone = models.CharField(max_length=20)
    order_date = models.DateTimeField(auto_now_add=True)
    delivery_type = models.CharField(
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.HOME,
    )
    delivery_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    wilaya = models.CharField(max_length=100)
    commune = models.CharField(max_length=100, blank=True, null=True)

    # -----------------------
    # Order workflow
    # -----------------------
    order_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )

    # Track important timestamps
    confirmed_at = models.DateTimeField(blank=True, null=True)
    on_the_way_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    returned_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)

    # -----------------------
    # Financials
    # -----------------------
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    def update_total(self):
        """
        Recalculate the total amount of the order (items + delivery fees).
        """
        items_total = self.items.aggregate(
            total=models.Sum(models.F("price") * models.F("quantity"))
        )["total"] or 0

        # Add delivery fees to items total
        self.total_amount = items_total + (self.delivery_fees or 0)
        self.save(update_fields=["total_amount"])

    def __str__(self):
        return f"Order #{self.pk} - {self.costumer_name}"

    # -----------------------
    # Validation rules
    # -----------------------
    def clean(self):
        """
        Ensure transitions are valid + stock checks are enforced
        """
        valid_transitions = {
            self.Status.PENDING: {self.Status.CONFIRMED, self.Status.CANCELLED},
            self.Status.CONFIRMED: {self.Status.ON_THE_WAY, self.Status.CANCELLED},
            self.Status.ON_THE_WAY: {self.Status.DELIVERED, self.Status.RETURNED_BY_CLIENT, self.Status.RETURNED_BY_OWNER},
            self.Status.DELIVERED: set(),
            self.Status.CANCELLED: set(),
            self.Status.RETURNED_BY_CLIENT: set(),
            self.Status.RETURNED_BY_OWNER: set(),
        }

        if self.pk:
            old_status = Order.objects.get(pk=self.pk).order_status
            allowed = valid_transitions.get(old_status, set())
            if self.order_status != old_status and self.order_status not in allowed:
                raise ValidationError({
                    "order_status": _(
                        f"Invalid transition from {old_status} → {self.order_status}"
                    )
                })

            # ✅ Stock validation
            if (
                (old_status == self.Status.PENDING and self.order_status == self.Status.CONFIRMED) or
                (old_status == self.Status.CONFIRMED and self.order_status == self.Status.ON_THE_WAY)
            ):
                for item in self.items.select_related("product_variant"):
                    pv = item.product_variant
                    if pv and pv.stock < item.quantity:
                        raise ValidationError({
                            "order_status": _(
                                f"Not enough stock for {pv} "
                                f"(required {item.quantity}, available {pv.stock})."
                            )
                        })

    # -----------------------
    # Save hook
    # -----------------------
    def save(self, *args, **kwargs):
        old_status = None
        if self.pk:
            old_status = Order.objects.get(pk=self.pk).order_status

        self.clean()  # ✅ validate stock + transitions

        now = timezone.now()
        if self.order_status == self.Status.CONFIRMED and not self.confirmed_at:
            self.confirmed_at = now
        elif self.order_status == self.Status.ON_THE_WAY and not self.on_the_way_at:
            self.on_the_way_at = now
        elif self.order_status == self.Status.DELIVERED and not self.delivered_at:
            self.delivered_at = now
        elif self.order_status in (self.Status.RETURNED_BY_CLIENT, self.Status.RETURNED_BY_OWNER) and not self.returned_at:
            self.returned_at = now
        elif self.order_status == self.Status.CANCELLED and not self.cancelled_at:
            self.cancelled_at = now

        super().save(*args, **kwargs)

        # -----------------------
        # Stock logic
        # -----------------------
        if old_status != self.order_status:
            if self.order_status == self.Status.ON_THE_WAY:
                self.decrement_stock()
            elif self.order_status in (self.Status.RETURNED_BY_CLIENT, self.Status.RETURNED_BY_OWNER):
                self.increment_stock()
    def decrement_stock(self):
        for item in self.items.all():
            if item.product_variant:
                item.product_variant.stock = models.F("stock") - item.quantity
                item.product_variant.save(update_fields=["stock"])

    def increment_stock(self):
        for item in self.items.all():
            if item.product_variant:
                item.product_variant.stock = models.F("stock") + item.quantity
                item.product_variant.save(update_fields=["stock"])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        db_index=True
    )
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    def __str__(self):
        return f"{self.product_variant} x {self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity

    def save(self, *args, **kwargs):
        if self.product_variant:
            # Use variant price if defined, otherwise fallback to product price
            if hasattr(self.product_variant, "price") and self.product_variant.price is not None:
                self.price = self.product_variant.price
            else:
                self.price = self.product_variant.product.price

        super().save(*args, **kwargs)

        # Recalculate total including delivery fees
        if self.order:
            self.order.update_total()

    def delete(self, *args, **kwargs):
        order = self.order
        super().delete(*args, **kwargs)
        if order:
            order.update_total()
