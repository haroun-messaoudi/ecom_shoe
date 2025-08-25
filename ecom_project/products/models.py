from django.db import models
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
import re
from django.core.exceptions import ValidationError

# Utility to clean names for file paths
def clean_name(name):
    # Replace spaces with underscores and remove invalid characters
    name = name.strip().replace(' ', '_')
    return re.sub(r'[^a-zA-Z0-9_-]', '', name)

def upload_to(instance, filename):
    # If instance is ProductImage, use the related product's name
    if hasattr(instance, 'product') and instance.product:
        base_name = clean_name(instance.product.name)
    else:
        base_name = clean_name(getattr(instance, 'name', 'unnamed'))
    return f'products/{base_name}/{filename}'

def upload_category_image(instance, filename):
    base_name = clean_name(instance.name)
    return f'categories/{base_name}/{filename}'

class Category(models.Model):
    name = models.CharField(max_length=255, db_index=True, unique=True)  # Add db_index and unique for faster lookups
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to=upload_category_image, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)  # Add db_index for filtering/sorting
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=255, db_index=True)  # Add db_index for search/filter
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)  # Add db_index for "new" queries
    updated_at = models.DateTimeField(auto_now=True)
    color = models.CharField(max_length=50, blank=True, null=True, db_index=True)  # Add db_index for filtering
    category = models.ForeignKey(
        Category,
        related_name='products',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        db_index=True
    )
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    sold = models.PositiveIntegerField(default=0, db_index=True)  # Add db_index for best-seller queries
    main_image = models.ImageField(upload_to=upload_to, blank=True, null=True)  # New main image field

    @property
    def is_new(self):
        days = 7
        return self.created_at >= timezone.now() - timedelta(days=days)

    def get_discounted_price(self):
        if self.discount_price:
            return max(self.price - self.discount_price, Decimal('0.00'))

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.full_clean()  # Enforce clean() on save
        super().save(*args, **kwargs)

    @classmethod
    def bulk_update_stock(cls, product_quantity_list):
        """
        Efficiently update stock for multiple products.
        product_quantity_list: list of (product_id, quantity_to_subtract)
        """
        products = cls.objects.filter(id__in=[pid for pid, _ in product_quantity_list])
        product_map = {p.id: p for p in products}
        for pid, qty in product_quantity_list:
            if pid in product_map:
                product_map[pid].stock = max(product_map[pid].stock - qty, 0)
        cls.objects.bulk_update(products, ['stock'])
    class Meta:
        indexes = [
            models.Index(fields=['sold']),
            models.Index(fields=['price']),
        ]
        
class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=upload_to)
    is_main = models.BooleanField(default=False, db_index=True)

    def save(self, *args, **kwargs):
        # If this is the first image for the product, set as main if none exists
        if not self.product.images.exclude(pk=self.pk).filter(is_main=True).exists():
            self.is_main = True
        elif self.is_main:
            # If this is set as main, unset others
            ProductImage.objects.filter(product=self.product, is_main=True).exclude(pk=self.pk).update(is_main=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.product.name}"

class ProductVariant(models.Model):
    product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE)
    size = models.CharField(max_length=50, db_index=True)
    stock = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        unique_together = ('product', 'size')
        indexes = [
            models.Index(fields=['stock']),
            models.Index(fields=['product', 'stock']),  # Composite index
        ]

    def __str__(self):
        return f"{self.product.name} - Size {self.size}"

# If you ever need to bulk create products, you can use Product.objects.bulk_create([...])
