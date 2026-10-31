from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone


class Invoice(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_PAID = 'paid'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Draft'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_PAID, 'Paid'),
        (STATUS_CANCELLED, 'Cancelled'),
    )

    number = models.CharField(max_length=32, unique=True, null=True, blank=True, editable=False)
    subscription = models.ForeignKey('subscriptions.Subscription', on_delete=models.CASCADE, related_name='invoices')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='invoices')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField(db_index=True)
    period_start = models.DateField()
    period_end = models.DateField()

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    notes = models.TextField(blank=True, default='')
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['subscription', 'period_start'],
                condition=~models.Q(status='cancelled'),
                name='unique_invoice_subscription_period_start',
            )
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"INV-{self.pk:05d}"
            super().save(update_fields=['number'])

    @property
    def balance(self):
        return (self.total or Decimal('0.00')) - (self.amount_paid or Decimal('0.00'))

    @property
    def is_overdue(self):
        today = timezone.now().date()
        return (
            self.status == self.STATUS_CONFIRMED
            and self.due_date is not None
            and self.due_date < today
            and self.balance > Decimal('0.00')
        )

    def __str__(self):
        return f"{self.number or f'INV-{self.pk}'} - {self.customer.email}"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=255)
    product = models.ForeignKey('catalog.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_discount = models.BooleanField(default=False)
    discount = models.ForeignKey('catalog.Discount', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def __str__(self):
        return f"{self.invoice} - {self.description}"


class Payment(models.Model):
    METHOD_CASH = 'cash'
    METHOD_CARD = 'card'
    METHOD_BANK_TRANSFER = 'bank_transfer'
    METHOD_UPI = 'upi'
    METHOD_CHEQUE = 'cheque'

    METHOD_CHOICES = (
        (METHOD_CASH, 'Cash'),
        (METHOD_CARD, 'Card'),
        (METHOD_BANK_TRANSFER, 'Bank Transfer'),
        (METHOD_UPI, 'UPI'),
        (METHOD_CHEQUE, 'Cheque'),
    )

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=METHOD_CARD)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    note = models.TextField(blank=True, default='')
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.id} for {self.invoice.number}: {self.amount}"


class BillingRun(models.Model):
    run_at = models.DateTimeField(auto_now_add=True)
    run_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='billing_runs')
    is_preview = models.BooleanField(default=False)
    total_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    generated = models.PositiveIntegerField(default=0)
    skipped = models.PositiveIntegerField(default=0)
    flagged = models.PositiveIntegerField(default=0)

    def __str__(self):
        preview_tag = " (Preview)" if self.is_preview else ""
        return f"BillingRun #{self.id} at {self.run_at:%Y-%m-%d %H:%M}{preview_tag}"


class BillingFlag(models.Model):
    REASON_ALREADY_INVOICED = 'already_invoiced'
    REASON_NOT_ACTIVE = 'not_active'
    REASON_PLAN_EXPIRED = 'plan_expired'
    REASON_NO_LINES = 'no_lines'
    REASON_DISCOUNT_EXHAUSTED = 'discount_exhausted'
    REASON_NO_TAX = 'no_tax'
    REASON_OTHER = 'other'

    REASON_CHOICES = (
        (REASON_ALREADY_INVOICED, 'Already Invoiced'),
        (REASON_NOT_ACTIVE, 'Not Active'),
        (REASON_PLAN_EXPIRED, 'Plan Expired'),
        (REASON_NO_LINES, 'No Lines'),
        (REASON_DISCOUNT_EXHAUSTED, 'Discount Exhausted'),
        (REASON_NO_TAX, 'No Tax'),
        (REASON_OTHER, 'Other'),
    )

    run = models.ForeignKey(BillingRun, on_delete=models.CASCADE, related_name='flags')
    subscription = models.ForeignKey('subscriptions.Subscription', on_delete=models.CASCADE, related_name='billing_flags')
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    message = models.TextField()
    resolved = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Flag on {self.subscription.number}: {self.get_reason_display()}"
