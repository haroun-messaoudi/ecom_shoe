from django.urls import path,include
from .views import (
    ProductListView, 
    CategoryListView, 
    ProductDetailView, 
    DiscountedProductListView, 
    TopOrderedProductsView, 
    NewProductListView,
    HomeDiscountedProductsView,
    HomeNewProductsView,
    HomeTopOrderedProductsView,
    ProductVariantsView,
    ProductSimilaritiesView,
    health_view
)

urlpatterns = [
    path('list',ProductListView.as_view(), name='product-list-create'),
    path('category/list', CategoryListView.as_view(), name='category-list-create'),
    path('<int:id>/', ProductDetailView.as_view(), name='product-detail'),
    path('discounted/', DiscountedProductListView.as_view(), name='discounted-product-list'),
    path('top-ordered/', TopOrderedProductsView.as_view(), name='top-ordered-products'),
    path('new/', NewProductListView.as_view(), name='new-product-list'),
    path('discounted-home/', HomeDiscountedProductsView.as_view(), name='discounted-home'),
    path('new-home/', HomeNewProductsView.as_view(), name='new-home'),
    path('top-ordered-home/', HomeTopOrderedProductsView.as_view(), name='top-ordered-home'),
    path('<int:id>/variants/', ProductVariantsView.as_view(), name='product-variant-list'),
    path('<int:id>/similar/', ProductSimilaritiesView.as_view(), name='similar-products'),
    path("health/", health_view),
]
