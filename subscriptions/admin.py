from django.contrib import admin
from .models import Subscription, SubscriptionLine


class SubscriptionLineInline(admin.TabularInline):
    model = SubscriptionLine
    extra = 1


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('number', 'customer', 'plan', 'status', 'start_date', 'next_invoice_date', 'total')
    list_filter = ('status', 'plan', 'start_date')
    search_fields = ('number', 'customer__email')
    inlines = [SubscriptionLineInline]


@admin.register(SubscriptionLine)
class SubscriptionLineAdmin(admin.ModelAdmin):
    list_display = ('subscription', 'product', 'variant', 'quantity', 'unit_price', 'tax')
    list_filter = ('product',)
