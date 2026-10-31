from django.contrib import admin
from .models import Invoice, InvoiceLine, Payment, BillingRun, BillingFlag


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 1


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('number', 'customer', 'status', 'invoice_date', 'due_date', 'total', 'amount_paid', 'balance', 'is_overdue')
    list_filter = ('status', 'invoice_date', 'due_date')
    search_fields = ('number', 'customer__email')
    inlines = [InvoiceLineInline, PaymentInline]


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'description', 'quantity', 'unit_price', 'amount', 'is_discount')
    list_filter = ('is_discount',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'method', 'amount', 'payment_date', 'recorded_by')
    list_filter = ('method', 'payment_date')
    search_fields = ('invoice__number', 'note')


class BillingFlagInline(admin.TabularInline):
    model = BillingFlag
    extra = 0


@admin.register(BillingRun)
class BillingRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'run_at', 'run_by', 'is_preview', 'total_due', 'generated', 'skipped', 'flagged')
    list_filter = ('is_preview', 'run_at')
    inlines = [BillingFlagInline]


@admin.register(BillingFlag)
class BillingFlagAdmin(admin.ModelAdmin):
    list_display = ('run', 'subscription', 'reason', 'resolved', 'created_at')
    list_filter = ('reason', 'resolved')
    search_fields = ('subscription__number', 'message')
