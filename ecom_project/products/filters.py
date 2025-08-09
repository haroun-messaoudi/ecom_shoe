from django.db.models import Case, When, F, DecimalField
import django_filters as filters
from .models import Product

class ProductFilter(filters.FilterSet):
    price_min = filters.NumberFilter(field_name="effective_price", lookup_expr='gte')
    price_max = filters.NumberFilter(field_name="effective_price", lookup_expr='lte')
    in_stock = filters.BooleanFilter(method='filter_in_stock')

    class Meta:
        model = Product
        fields = ['category', 'price_min', 'price_max', 'in_stock']

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(variants__stock__gt=0).distinct()
        return queryset
