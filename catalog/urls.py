from django.urls import path
from . import views

app_name = 'catalog'

urlpatterns = [
    # Catalog Landing Page
    path('', views.catalog_dashboard, name='dashboard'),

    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.product_create, name='product_create'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/<int:pk>/variants/add/', views.product_variant_add, name='product_variant_add'),
    path('products/<int:pk>/variants/<int:variant_pk>/delete/', views.product_variant_delete, name='product_variant_delete'),

    # Plans
    path('plans/', views.plan_list, name='plan_list'),
    path('plans/add/', views.plan_create, name='plan_create'),
    path('plans/<int:pk>/', views.plan_detail, name='plan_detail'),
    path('plans/<int:pk>/edit/', views.plan_update, name='plan_update'),
    path('plans/<int:pk>/delete/', views.plan_delete, name='plan_delete'),
    path('plans/<int:pk>/duplicate/', views.plan_duplicate, name='plan_duplicate'),

    # Taxes
    path('taxes/', views.tax_list, name='tax_list'),
    path('taxes/add/', views.tax_create, name='tax_create'),
    path('taxes/<int:pk>/edit/', views.tax_update, name='tax_update'),
    path('taxes/<int:pk>/delete/', views.tax_delete, name='tax_delete'),

    # Discounts
    path('discounts/', views.discount_list, name='discount_list'),
    path('discounts/add/', views.discount_create, name='discount_create'),
    path('discounts/<int:pk>/', views.discount_detail, name='discount_detail'),
    path('discounts/<int:pk>/edit/', views.discount_update, name='discount_update'),
    path('discounts/<int:pk>/delete/', views.discount_delete, name='discount_delete'),

    # Quotation Templates
    path('templates/', views.quotation_template_list, name='template_list'),
    path('templates/add/', views.quotation_template_create, name='template_create'),
    path('templates/<int:pk>/', views.quotation_template_detail, name='template_detail'),
    path('templates/<int:pk>/edit/', views.quotation_template_update, name='template_update'),
    path('templates/<int:pk>/delete/', views.quotation_template_delete, name='template_delete'),
    path('templates/<int:pk>/lines/add/', views.quotation_template_line_add, name='template_line_add'),
    path('templates/<int:pk>/lines/<int:line_pk>/delete/', views.quotation_template_line_delete, name='template_line_delete'),
]
