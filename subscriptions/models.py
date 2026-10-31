from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone


class Subscription(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_QUOTATION = 'quotation'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_CLOSED = 'closed'

    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Draft'),
        (STATUS_QUOTATION, 'Quotation'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_CLOSED, 'Closed'),
    )

    number = models.CharField(max_length=32, unique=True, null=True, blank=True, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey('catalog.Plan', on_delete=models.PROTECT, related_name='subscriptions')
    template = models.ForeignKey('catalog.QuotationTemplate', on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    discount = models.ForeignKey('catalog.Discount', on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    start_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=15)
    next_invoice_date = models.DateField(null=True, blank=True, db_index=True)
    quotation_valid_until = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_subscriptions')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"SUB-{self.pk:04d}"
            super().save(update_fields=['number'])

    @property
    def subtotal(self):
        return sum((line.amount for line in self.lines.all()), Decimal('0.00'))

    @property
    def tax_total(self):
        return sum((line.tax_amount for line in self.lines.all()), Decimal('0.00'))

    @property
    def total(self):
        return self.subtotal + self.tax_total

    def __str__(self):
        return f"{self.number or f'SUB-{self.pk}'} - {self.customer.email}"


class SubscriptionLine(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='+')
    variant = models.ForeignKey('catalog.ProductVariant', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax = models.ForeignKey('catalog.Tax', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    @property
    def amount(self):
        return (Decimal(self.quantity) * self.unit_price).quantize(Decimal('0.01'))

    @property
    def tax_amount(self):
        if self.tax and self.tax.rate:
            rate = Decimal(str(self.tax.rate)) / Decimal('100.0')
            return (self.amount * rate).quantize(Decimal('0.01'))
        return Decimal('0.00')

    @property
    def total_amount(self):
        return self.amount + self.tax_amount

    def __str__(self):
        return f"{self.subscription} - {self.product.name} x {self.quantity}"
