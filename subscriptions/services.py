import calendar
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone

from .models import Subscription, SubscriptionLine

# Pricing fallback helpers if catalog.pricing is not yet created by P2
try:
    from catalog.pricing import get_line_price, calculate_line_tax
except ImportError:
    def get_line_price(product, variant=None):
        price = product.sales_price
        if variant and variant.extra_price:
            price += variant.extra_price
        return price

    def calculate_line_tax(amount, tax):
        if not tax or not tax.rate:
            return Decimal('0.00')
        from decimal import ROUND_HALF_UP
        return (amount * (tax.rate / Decimal('100.0'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def add_plan_period(start_date, billing_period):
    """
    Computes end of term / next period date given a billing period.
    """
    if billing_period == 'daily':
        return start_date + timedelta(days=1)
    elif billing_period == 'weekly':
        return start_date + timedelta(weeks=1)
    elif billing_period == 'monthly':
        year = start_date.year + (start_date.month // 12)
        month = (start_date.month % 12) + 1
        day = min(start_date.day, calendar.monthrange(year, month)[1])
        return start_date.replace(year=year, month=month, day=day)
    elif billing_period == 'yearly':
        try:
            return start_date.replace(year=start_date.year + 1)
        except ValueError:
            return start_date.replace(year=start_date.year + 1, day=28)
    return start_date + timedelta(days=30)


def create_subscription_from_template(customer, template, start_date=None, payment_terms_days=15, created_by=None):
    """
    Creates a new Subscription from a QuotationTemplate:
    - Copies template product lines into SubscriptionLines.
    - Resolves unit price (product + variant extra price).
    - Uses product tax.
    - Sets quotation_valid_until = today + template.validity_days.
    - Sets status = Draft.
    - Sets next_invoice_date = start_date.
    - Sets expiry_date = start_date + 1 billing period.
    """
    today = timezone.now().date()
    if start_date is None:
        start_date = today

    expiry_date = add_plan_period(start_date, template.plan.billing_period)
    quotation_valid_until = today + timedelta(days=template.validity_days)

    subscription = Subscription.objects.create(
        customer=customer,
        plan=template.plan,
        template=template,
        status=Subscription.STATUS_DRAFT,
        start_date=start_date,
        expiry_date=expiry_date,
        payment_terms_days=payment_terms_days,
        next_invoice_date=start_date,
        quotation_valid_until=quotation_valid_until,
        created_by=created_by,
    )

    for tmpl_line in template.lines.select_related('product', 'variant', 'product__tax'):
        unit_price = get_line_price(tmpl_line.product, tmpl_line.variant)
        tax = tmpl_line.product.tax

        SubscriptionLine.objects.create(
            subscription=subscription,
            product=tmpl_line.product,
            variant=tmpl_line.variant,
            quantity=tmpl_line.quantity,
            unit_price=unit_price,
            tax=tax,
        )

    return subscription


def close_expired_subscriptions(today=None):
    """
    Auto-closes active subscriptions whose plan.auto_close is True and expiry_date < today.
    """
    if today is None:
        today = timezone.now().date()

    expired = Subscription.objects.filter(
        status=Subscription.STATUS_ACTIVE,
        plan__auto_close=True,
        expiry_date__lt=today,
    )
    count = expired.update(status=Subscription.STATUS_CLOSED)
    return count

