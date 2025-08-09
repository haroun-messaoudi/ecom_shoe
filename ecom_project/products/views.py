from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.generics import (
    ListAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from .models import Product, Category
from .serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    CategorySerializer,
    ProductImageSerializer,
    ProductVariantSerializer,
)
from products.filters import ProductFilter
from django.http import JsonResponse
from django.urls import path

def health_view(request):
    return JsonResponse({"status": "ok", "uptime": "healthy"}, status=200)



# Pagination
class StandardPagination(PageNumberPagination):
    page_size_query_param = 'page_size'
    max_page_size = 100

# Cache TTLs
FIVE_MINUTES = 60 * 5     
HEIGHT_MINUTES = 60 * 8    
SHORT_CACHE = 60 * 3      

@method_decorator(cache_page(FIVE_MINUTES), name='dispatch')
class ProductListView(ListAPIView):
    """
    /api/products/list
    supports ?page, ?page_size, ?search, ?category, plus any ProductFilter fields
    """
    serializer_class = ProductListSerializer
    pagination_class = StandardPagination
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class  = ProductFilter
    search_fields    = ['name']
    ordering_fields = ['price', 'created_at', 'name']
    def get_queryset(self):
        return (
            Product.objects
                .only('id', 'name', 'price', 'discount_price', 'category', 'main_image', 'created_at')
                .select_related('category')
        )

@method_decorator(cache_page(FIVE_MINUTES), name='dispatch')
class DiscountedProductListView(ListAPIView):
    """
    /api/products/discounted
    """
    serializer_class = ProductListSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        return (
            Product.objects
                .only('id', 'name', 'price', 'discount_price', 'category', 'main_image', 'created_at')
                .exclude(discount_price__isnull=True)
                .exclude(discount_price=Decimal('0.00'))
                .select_related('category')
        )

@method_decorator(cache_page(FIVE_MINUTES), name='dispatch')
class NewProductListView(ListAPIView):
    """
    /api/products/new-products
    """
    serializer_class = ProductListSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        cutoff = timezone.now() - timedelta(days=7)
        return (
            Product.objects
                .only('id', 'name', 'price', 'discount_price', 'category', 'main_image', 'created_at')
                .filter(created_at__gte=cutoff)
                .select_related('category')
        )

@method_decorator(cache_page(FIVE_MINUTES), name='dispatch')
class TopOrderedProductsView(ListAPIView):
    """
    /api/products/top-ordered
    """
    serializer_class = ProductListSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        return (
            Product.objects
                .only('id', 'name', 'price', 'discount_price', 'category', 'main_image', 'created_at')
                .order_by('-sold')
                .select_related('category')
        )

@method_decorator(cache_page(HEIGHT_MINUTES), name='dispatch')
class ProductDetailView(RetrieveUpdateDestroyAPIView):
    """
    /api/products/<id>/
    """
    queryset         = (
        Product.objects
               .only(
                   'id', 'name', 'description', 'price', 'discount_price', 'category',
                   'main_image', 'created_at', 'updated_at'
               )
               .select_related('category')
               .prefetch_related('images', 'variants')
    )
    serializer_class = ProductDetailSerializer
    lookup_field     = 'id'

@method_decorator(cache_page(FIVE_MINUTES), name='dispatch')
class CategoryListView(ListAPIView):
    """
    /api/products/category/list
    """
    serializer_class = CategorySerializer
    pagination_class = None  # return all categories without pagination

    def list(self, request, *args, **kwargs):
        qs = Category.objects.all()
        data = self.serializer_class(qs, many=True).data
        return Response(data)

@method_decorator(cache_page(FIVE_MINUTES), name='dispatch')
class HomeDiscountedProductsView(ListAPIView):
    serializer_class = ProductListSerializer
    pagination_class = None  # No pagination, just top 4

    def get_queryset(self):
        return (
            Product.objects
                .only('id', 'name', 'price', 'discount_price', 'category', 'main_image', 'created_at')
                .exclude(discount_price__isnull=True)
                .exclude(discount_price=0)
                .order_by('-discount_price')[:4]
                .select_related('category')
        )

@method_decorator(cache_page(FIVE_MINUTES), name='dispatch')
class HomeNewProductsView(ListAPIView):
    serializer_class = ProductListSerializer
    pagination_class = None

    def get_queryset(self):
        cutoff = timezone.now() - timedelta(days=7)
        return (
            Product.objects
                .only('id', 'name', 'price', 'discount_price', 'category', 'main_image', 'created_at')
                .filter(created_at__gte=cutoff)
                .order_by('-created_at')[:4]
                .select_related('category')
        )

@method_decorator(cache_page(FIVE_MINUTES), name='dispatch')
class HomeTopOrderedProductsView(ListAPIView):
    serializer_class = ProductListSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Product.objects
                .only('id', 'name', 'price', 'discount_price', 'category', 'main_image', 'created_at')
                .order_by('-sold')[:4]
                .select_related('category')
        )

# @method_decorator(cache_page(SHORT_CACHE), name='dispatch')
# class ProductExtrasView(APIView):
#     def get(self, request, id):
#         product = Product.objects.get(id=id)
#         images = ProductImageSerializer(product.images.all(), many=True).data
#         variants = ProductVariantSerializer(product.variants.all(), many=True).data
#         return Response({
#             "images": images,
#             "variants": variants,
#         })

class ProductVariantsView(APIView):
    """
    /api/products/<id>/variants/
    Returns only the variants for a product (not cached).
    """
    def get(self, request, id):
        try:
            product = Product.objects.get(id=id)
        except Product.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        variants = ProductVariantSerializer(product.variants.all(), many=True).data
        return Response({"variants": variants})
    

class ProductSimilaritiesView(APIView):
    """
    /api/products/<id>/similar/
    Returns similar products based on category.
    """
    def get(self, request, id):
        try:
            product = Product.objects.get(id=id)
        except Product.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        similar_products = (
            Product.objects
                .filter(category=product.category)
                .exclude(id=product.id)
                .only('id', 'name', 'price', 'discount_price', 'category', 'main_image', 'created_at')
                .order_by('?')[:4]
        )
        serializer = ProductListSerializer(similar_products, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)