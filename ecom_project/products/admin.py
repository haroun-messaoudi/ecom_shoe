from decimal import Decimal
from django.contrib import admin, messages
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.forms.models import BaseInlineFormSet

from .models import Product, Category, ProductImage, ProductVariant


class DiscountedListFilter(admin.SimpleListFilter):
    title = 'Discounted'
    parameter_name = 'discounted'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Discounted'),
            ('no', 'Not Discounted'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.exclude(discount_price__isnull=True).exclude(discount_price=Decimal('0.00'))
        if self.value() == 'no':
            return queryset.filter(discount_price__isnull=True) | queryset.filter(discount_price=Decimal('0.00'))
        return queryset


class ProductImageInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        image_count = sum(
            1 for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False)
        )
        if image_count < 1:
            raise ValidationError(_('Please upload at least one image for this product.'))


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("image", "is_main", "image_preview")
    readonly_fields = ("image_preview",)
    formset = ProductImageInlineFormSet
    show_change_link = True

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:100px; width:auto; object-fit:contain; border:1px solid #ccc;" loading="lazy"/>',
                obj.image.url
            )
        return "(no image)"
    image_preview.short_description = "Preview"


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ("size", "stock")
    min_num = 1
    verbose_name = "Available Size"
    verbose_name_plural = "Available Sizes"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id", "name", "price", "discount_price", "sold"
    )
    list_display_links = ("id", "name")
    list_filter = ("category", DiscountedListFilter)
    list_per_page = 25
    list_max_show_all = 200
    search_fields = ("name",)
    ordering = ("-id",)

    readonly_fields = ("main_image_preview", "get_discounted_price")
    fields = (
        "name", "description", "price", "discount_price", "get_discounted_price",
        "category", "main_image_preview", "color", "sold",
    )

    inlines = [ProductImageInline, ProductVariantInline]

    def get_queryset(self, request):
        # Avoid heavy joins for admin list view
        return super().get_queryset(request).only(
            'id', 'name', 'price', 'discount_price', 'sold', 'category', 'color'
        )

    def get_discounted_price(self, obj):
        return obj.get_discounted_price()
    get_discounted_price.short_description = "Discounted Price"

    def main_image_preview(self, obj):
        main_img = obj.main_image
        if not main_img:
            main_img_obj = obj.images.filter(is_main=True).only('image').first()
            if main_img_obj and main_img_obj.image:
                main_img = main_img_obj.image
        if main_img:
            return format_html(
                '<img src="{}" style="height:60px; width:auto; object-fit:contain; border:1px solid #ccc;" loading="lazy"/>',
                main_img.url
            )
        return "(no image)"
    main_image_preview.short_description = "Main Image"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        messages.success(request, _('Product saved successfully.'))

    def save_formset(self, request, form, formset, change):
        try:
            formset.save()
        except ValidationError as e:
            self.message_user(request, str(e), level=messages.ERROR)
            raise


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")  # ⚠️ Removed image preview here too
    list_display_links = ("id", "name")
    search_fields = ("name",)
    ordering = ("name",)
    fields = ("name", "description", "image", "category_image_preview")
    readonly_fields = ("category_image_preview",)

    def category_image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:50px; width:auto; object-fit:contain; border:1px solid #ccc;" loading="lazy"/>',
                obj.image.url
            )
        return "(no image)"
    category_image_preview.short_description = "Image"


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    search_fields = ["product__name", "size"]  # what you want searchable
    list_display = ["id", "product", "size"]