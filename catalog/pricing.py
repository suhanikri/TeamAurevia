import datetime
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from .models import Discount


def get_line_price(product, variant=None) -> Decimal:
    """
    Returns the line unit price: product.sales_price + (variant.extra_price if variant else 0).
    Example: product 1000 + Odoo brand 560 = 1560.00.
    """
    if product is None:
        return Decimal('0.00')

    base_price = Decimal(str(product.sales_price)) if getattr(product, 'sales_price', None) is not None else Decimal('0.00')
    extra_price = Decimal('0.00')
    if variant and getattr(variant, 'extra_price', None) is not None:
        extra_price = Decimal(str(variant.extra_price))

    return (base_price + extra_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate_line_tax(amount, tax) -> Decimal:
    """
    Calculates line tax: amount * tax.rate / 100 rounded to 2 decimal places (ROUND_HALF_UP).
    Returns Decimal('0.00') if tax is None or tax.rate is None.
    """
    if not tax or getattr(tax, 'rate', None) is None or amount is None:
        return Decimal('0.00')

    amt = Decimal(str(amount))
    rate = Decimal(str(tax.rate))
    tax_amount = (amt * rate / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return tax_amount


def get_applicable_discounts(subscription, on=None) -> list:
    """
    Evaluates and returns a list of tuples (discount, amount) where amount is a
    POSITIVE Decimal rounded to 2 decimals (ROUND_HALF_UP).

    Rules:
    - Candidates are discounts where discount.is_usable(on) is True.
    - A whole-subscription discount applies only if subscription.discount_id equals that discount's id.
      Base amount = subscription.subtotal.
    - A discount with scope "products" applies automatically to lines whose product is in discount.products.
      Base amount = sum of those lines' amounts.
    - Skip if base amount < min_purchase, or total quantity of the applicable lines < min_quantity.
    - Fixed discount = value (never more than the base amount).
    - Percent discount = base * value / 100.
    - Return an empty list if nothing applies. Never raise for a normal subscription.
    """
    if not subscription:
        return []

    # Normalize 'on' date (if passed datetime, convert to date)
    if on is not None and hasattr(on, 'date') and callable(on.date):
        on = on.date()

    results = []
    seen_discount_ids = set()

    # Pre-fetch all lines for efficient evaluation
    try:
        lines = list(subscription.lines.all())
    except Exception:
        lines = []

    # 1. Evaluate Whole-Subscription Discount (attached to subscription.discount)
    # "A whole-subscription discount applies only if subscription.discount_id equals that discount's id."
    whole_discount = getattr(subscription, 'discount', None)
    if whole_discount and whole_discount.scope == Discount.SCOPE_ALL:
        if whole_discount.is_usable(on):
            base_amount = getattr(subscription, 'subtotal', Decimal('0.00'))
            if base_amount is None:
                base_amount = sum((getattr(line, 'amount', Decimal('0.00')) for line in lines), Decimal('0.00'))

            total_quantity = sum((getattr(line, 'quantity', 0) for line in lines), 0)

            min_purchase = whole_discount.min_purchase or Decimal('0.00')
            min_quantity = whole_discount.min_quantity or 0

            # Skip if thresholds not met or no base amount
            if base_amount > Decimal('0.00') and base_amount >= min_purchase and total_quantity >= min_quantity:
                val = Decimal(str(whole_discount.value))
                if whole_discount.discount_type == Discount.TYPE_FIXED:
                    discount_amount = min(val, base_amount)
                else:  # percent
                    discount_amount = base_amount * val / Decimal('100')

                amount = discount_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if amount > Decimal('0.00'):
                    results.append((whole_discount, amount))
                    seen_discount_ids.add(whole_discount.id)

    # 2. Evaluate Product-Scope Discounts
    # "A discount with scope 'products' applies automatically to lines whose product is in discount.products."
    # Candidates are discounts where discount.is_usable(on) is True
    product_discounts = Discount.objects.filter(
        is_active=True,
        scope=Discount.SCOPE_PRODUCTS
    ).prefetch_related('products')

    for disc in product_discounts:
        if disc.id in seen_discount_ids:
            continue

        if not disc.is_usable(on):
            continue

        # Find matching lines
        disc_product_ids = set(disc.products.values_list('id', flat=True))
        matching_lines = [line for line in lines if getattr(line, 'product_id', None) in disc_product_ids]

        if not matching_lines:
            continue

        base_amount = sum((getattr(line, 'amount', Decimal('0.00')) for line in matching_lines), Decimal('0.00'))
        total_quantity = sum((getattr(line, 'quantity', 0) for line in matching_lines), 0)

        min_purchase = disc.min_purchase or Decimal('0.00')
        min_quantity = disc.min_quantity or 0

        # Skip if threshold not met
        if base_amount <= Decimal('0.00') or base_amount < min_purchase or total_quantity < min_quantity:
            continue

        val = Decimal(str(disc.value))
        if disc.discount_type == Discount.TYPE_FIXED:
            discount_amount = min(val, base_amount)
        else:  # percent
            discount_amount = base_amount * val / Decimal('100')

        amount = discount_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if amount > Decimal('0.00'):
            results.append((disc, amount))
            seen_discount_ids.add(disc.id)

    return results
