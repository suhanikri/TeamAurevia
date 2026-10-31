from decimal import Decimal
from django.db import models
from django.utils import timezone


class Tax(models.Model):
    name = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Percentage tax rate (e.g. 18.00 for 18%)")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Tax'
        verbose_name_plural = 'Taxes'

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class Product(models.Model):
    PRODUCT_TYPE_CHOICES = (
        ('software', 'Software'),
        ('service', 'Service'),
        ('addon', 'Add-on'),
        ('other', 'Other'),
    )

    name = models.CharField(max_length=200)
    product_type = models.CharField(max_length=50, choices=PRODUCT_TYPE_CHOICES, default='software')
    sales_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax = models.ForeignKey(Tax, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    notes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    attribute = models.CharField(max_length=100, help_text="e.g. Brand, Tier, Region")
    value = models.CharField(max_length=100, help_text="e.g. Odoo, Pro, US-East")
    extra_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['product', 'attribute', 'value'], name='unique_product_attribute_value')
        ]

    def __str__(self):
        return f"{self.product.name} ({self.attribute}: {self.value} +{self.extra_price})"


class Plan(models.Model):
    PERIOD_DAILY = 'daily'
    PERIOD_WEEKLY = 'weekly'
    PERIOD_MONTHLY = 'monthly'
    PERIOD_YEARLY = 'yearly'

    BILLING_PERIOD_CHOICES = (
        (PERIOD_DAILY, 'Daily'),
        (PERIOD_WEEKLY, 'Weekly'),
        (PERIOD_MONTHLY, 'Monthly'),
        (PERIOD_YEARLY, 'Yearly'),
    )

    name = models.CharField(max_length=150)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    billing_period = models.CharField(max_length=20, choices=BILLING_PERIOD_CHOICES, default=PERIOD_MONTHLY)
    min_quantity = models.PositiveIntegerField(default=1)
    available_from = models.DateField(null=True, blank=True)
    available_to = models.DateField(null=True, blank=True)

    # 4 admin-controlled flags
    auto_close = models.BooleanField(default=False)
    is_closable = models.BooleanField(default=True)
    is_pausable = models.BooleanField(default=True)
    is_renewable = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)

    def is_available(self, on=None):
        if not self.is_active:
            return False
        if on is None:
            on = timezone.now().date()
        if self.available_from and on < self.available_from:
            return False
        if self.available_to and on > self.available_to:
            return False
        return True

    def __str__(self):
        return f"{self.name} ({self.get_billing_period_display()})"


class Discount(models.Model):
    TYPE_PERCENT = 'percent'
    TYPE_FIXED = 'fixed'

    DISCOUNT_TYPE_CHOICES = (
        (TYPE_PERCENT, 'Percentage'),
        (TYPE_FIXED, 'Fixed Amount'),
    )

    SCOPE_ALL = 'all'
    SCOPE_PRODUCTS = 'products'

    SCOPE_CHOICES = (
        (SCOPE_ALL, 'Whole Subscription'),
        (SCOPE_PRODUCTS, 'Specific Products'),
    )

    name = models.CharField(max_length=150)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default=TYPE_PERCENT)
    value = models.DecimalField(max_digits=12, decimal_places=2, help_text="Percentage or fixed amount")
    min_purchase = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    min_quantity = models.PositiveIntegerField(default=0)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Leave blank for unlimited")
    used_count = models.PositiveIntegerField(default=0)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_ALL)
    products = models.ManyToManyField(Product, blank=True, related_name='discounts')
    is_active = models.BooleanField(default=True)

    def is_usable(self, on=None):
        if not self.is_active:
            return False
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False
        if on is None:
            on = timezone.now().date()
        if self.start_date and on < self.start_date:
            return False
        if self.end_date and on > self.end_date:
            return False
        return True

    def __str__(self):
        if self.discount_type == self.TYPE_PERCENT:
            return f"{self.name} ({self.value}%)"
        return f"{self.name} (₹{self.value})"


class QuotationTemplate(models.Model):
    name = models.CharField(max_length=150)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='templates')
    validity_days = models.PositiveIntegerField(default=30)
    notes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class QuotationTemplateLine(models.Model):
    template = models.ForeignKey(QuotationTemplate, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='+')
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.template.name} - {self.product.name} x {self.quantity}"
