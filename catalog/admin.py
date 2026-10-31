from django.contrib import admin
from .models import (
    Tax,
    Product,
    ProductVariant,
    Plan,
    Discount,
    QuotationTemplate,
    QuotationTemplateLine,
)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_type', 'sales_price', 'cost_price', 'tax', 'is_active')
    list_filter = ('product_type', 'is_active')
    search_fields = ('name',)
    inlines = [ProductVariantInline]


class QuotationTemplateLineInline(admin.TabularInline):
    model = QuotationTemplateLine
    extra = 1


@admin.register(QuotationTemplate)
class QuotationTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'plan', 'validity_days', 'is_active')
    list_filter = ('is_active', 'plan')
    search_fields = ('name',)
    inlines = [QuotationTemplateLineInline]


@admin.register(Tax)
class TaxAdmin(admin.ModelAdmin):
    list_display = ('name', 'rate', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('product', 'attribute', 'value', 'extra_price')
    list_filter = ('attribute',)
    search_fields = ('product__name', 'value')


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'billing_period', 'price', 'is_active', 'auto_close', 'is_closable', 'is_pausable', 'is_renewable')
    list_filter = ('billing_period', 'is_active', 'auto_close', 'is_closable', 'is_pausable', 'is_renewable')
    search_fields = ('name',)


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ('name', 'discount_type', 'value', 'scope', 'used_count', 'usage_limit', 'is_active', 'start_date', 'end_date')
    list_filter = ('discount_type', 'scope', 'is_active')
    search_fields = ('name',)
    filter_horizontal = ('products',)


@admin.register(QuotationTemplateLine)
class QuotationTemplateLineAdmin(admin.ModelAdmin):
    list_display = ('template', 'product', 'variant', 'quantity')
