import calendar
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction, IntegrityError
from django.utils import timezone

from catalog.models import Plan, Discount
from subscriptions.models import Subscription
from .models import Invoice, InvoiceLine, BillingRun, BillingFlag

# Pricing & Tax Fallback Helpers
try:
    from catalog.pricing import get_line_price, calculate_line_tax, get_applicable_discounts
except ImportError:
    def get_line_price(product, variant=None):
        price = product.sales_price
        if variant and variant.extra_price:
            price += variant.extra_price
        return price

    def calculate_line_tax(amount, tax):
        if not tax or not tax.rate:
            return Decimal('0.00')
        return (amount * (tax.rate / Decimal('100.0'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def get_applicable_discounts(subscription, on=None):
        if on is None:
            on = timezone.now().date()
        discount = subscription.discount
        if not discount or not discount.is_usable(on):
            return []

        lines = list(subscription.lines.all())
        if discount.scope == Discount.SCOPE_PRODUCTS:
            eligible_products = set(discount.products.all())
            target_lines = [l for l in lines if l.product in eligible_products]
        else:
            target_lines = lines

        total_qty = sum(l.quantity for l in target_lines)
        total_amt = sum(l.amount for l in target_lines)

        if discount.min_quantity and total_qty < discount.min_quantity:
            return []
        if discount.min_purchase and total_amt < discount.min_purchase:
            return []

        if discount.discount_type == Discount.TYPE_PERCENT:
            amount = (total_amt * (discount.value / Decimal('100.0'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            amount = min(discount.value, total_amt).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if amount > Decimal('0.00'):
            return [(discount, amount)]
        return []


def add_plan_period(start_date, billing_period):
    """
    Computes end of term or advances date by one plan period.
    """
    if billing_period == Plan.PERIOD_DAILY:
        return start_date + timedelta(days=1)
    elif billing_period == Plan.PERIOD_WEEKLY:
        return start_date + timedelta(weeks=1)
    elif billing_period == Plan.PERIOD_MONTHLY:
        year = start_date.year + (start_date.month // 12)
        month = (start_date.month % 12) + 1
        day = min(start_date.day, calendar.monthrange(year, month)[1])
        return start_date.replace(year=year, month=month, day=day)
    elif billing_period == Plan.PERIOD_YEARLY:
        try:
            return start_date.replace(year=start_date.year + 1)
        except ValueError:
            return start_date.replace(year=start_date.year + 1, day=28)
    return start_date + timedelta(days=30)


def calculate_billing_period(period_start, billing_period):
    """
    Calculates (period_start, period_end) for an invoice.
    period_end is period_start + 1 billing period minus 1 day.
    """
    next_period_start = add_plan_period(period_start, billing_period)
    period_end = next_period_start - timedelta(days=1)
    return period_start, period_end


def evaluate_subscription_for_billing(sub, today):
    """
    Evaluates a candidate subscription.
    Returns:
      (outcome, reason, message, period_start, period_end)
      where outcome in ('ready', 'skipped', 'flagged')
    """
    # 1. Active status check
    if sub.status != Subscription.STATUS_ACTIVE:
        return (
            'flagged',
            BillingFlag.REASON_NOT_ACTIVE,
            f"Subscription status is '{sub.get_status_display()}', not Active.",
            None,
            None,
        )

    # 2. Plan validity / expiration check
    if not sub.plan.is_available(today):
        return (
            'flagged',
            BillingFlag.REASON_PLAN_EXPIRED,
            f"Plan '{sub.plan.name}' is outside its availability window ({sub.plan.available_from} to {sub.plan.available_to}).",
            None,
            None,
        )

    # 3. Product lines check
    lines = list(sub.lines.all())
    if not lines:
        return (
            'flagged',
            BillingFlag.REASON_NO_LINES,
            "Subscription has no product lines configured.",
            None,
            None,
        )

    # 4. Tax configuration check (every line must have a tax rule assigned)
    if any(line.tax is None for line in lines):
        return (
            'flagged',
            BillingFlag.REASON_NO_TAX,
            "One or more subscription product lines have no tax rule assigned.",
            None,
            None,
        )

    # 5. Discount validity check
    if sub.discount and not sub.discount.is_usable(today):
        return (
            'flagged',
            BillingFlag.REASON_DISCOUNT_EXHAUSTED,
            f"Discount '{sub.discount.name}' is expired, inactive, or exhausted.",
            None,
            None,
        )

    # 6. Billing period calculation & double-billing check
    period_start = sub.next_invoice_date or sub.start_date
    period_start, period_end = calculate_billing_period(period_start, sub.plan.billing_period)

    # Check for existing non-cancelled invoice for this exact subscription and period_start
    existing_invoice = Invoice.objects.filter(
        subscription=sub,
        period_start=period_start,
    ).exclude(status=Invoice.STATUS_CANCELLED).first()

    if existing_invoice:
        return (
            'skipped',
            BillingFlag.REASON_ALREADY_INVOICED,
            f"Invoice {existing_invoice.number} already exists for period {period_start} to {period_end}.",
            period_start,
            period_end,
        )

    return ('ready', None, None, period_start, period_end)


def preview_billing(today=None):
    """
    Dry run of billing.
    Finds Subscriptions due (next_invoice_date <= today and not closed).
    Returns lists of ready, skipped, and flagged subscriptions.
    Does NOT write anything to the database.
    """
    if today is None:
        today = timezone.now().date()

    candidates = Subscription.objects.filter(
        next_invoice_date__lte=today,
    ).exclude(
        status=Subscription.STATUS_CLOSED,
    ).select_related(
        'customer', 'plan', 'template', 'discount',
    ).prefetch_related(
        'lines', 'lines__product', 'lines__variant', 'lines__tax',
    ).order_by('id')

    ready = []
    skipped = []
    flagged = []

    for sub in candidates:
        outcome, reason, message, period_start, period_end = evaluate_subscription_for_billing(sub, today)

        if outcome == 'flagged':
            flagged.append({
                'subscription': sub,
                'reason': reason,
                'message': message,
            })
        elif outcome == 'skipped':
            skipped.append({
                'subscription': sub,
                'message': message,
            })
        elif outcome == 'ready':
            ready.append(sub)

    return {
        'run': None,
        'ready': ready,
        'generated': [],
        'skipped': skipped,
        'flagged': flagged,
    }


def run_billing(today=None, user=None):
    """
    Executes the Billing Integrity Engine:
    - Evaluates all due subscriptions.
    - Inside atomic transactions per subscription, creates Invoice and InvoiceLine records.
    - Applies negative discount lines and increments discount.used_count atomically.
    - Advances subscription.next_invoice_date by one plan period.
    - Saves BillingRun and BillingFlag records.
    - Enforces DB-level UniqueConstraint so duplicates are impossible.
    """
    if today is None:
        today = timezone.now().date()

    candidates = Subscription.objects.filter(
        next_invoice_date__lte=today,
    ).exclude(
        status=Subscription.STATUS_CLOSED,
    ).select_related(
        'customer', 'plan', 'template', 'discount',
    ).prefetch_related(
        'lines', 'lines__product', 'lines__variant', 'lines__tax',
    ).order_by('id')

    generated = []
    skipped = []
    flagged = []
    total_due = Decimal('0.00')

    for sub in candidates:
        outcome, reason, message, period_start, period_end = evaluate_subscription_for_billing(sub, today)

        if outcome == 'flagged':
            flagged.append({
                'subscription': sub,
                'reason': reason,
                'message': message,
            })
            continue

        if outcome == 'skipped':
            skipped.append({
                'subscription': sub,
                'message': message,
            })
            continue

        # Ready subscription -> generate invoice in its own atomic transaction
        try:
            with transaction.atomic():
                due_date = today + timedelta(days=sub.payment_terms_days)

                invoice = Invoice.objects.create(
                    subscription=sub,
                    customer=sub.customer,
                    status=Invoice.STATUS_DRAFT,
                    invoice_date=today,
                    due_date=due_date,
                    period_start=period_start,
                    period_end=period_end,
                )

                subtotal = Decimal('0.00')
                tax_total = Decimal('0.00')
                discount_total = Decimal('0.00')

                # Create lines for subscription products
                for s_line in sub.lines.select_related('product', 'variant', 'tax'):
                    line_subtotal = (Decimal(s_line.quantity) * s_line.unit_price).quantize(Decimal('0.01'))
                    tax_rate = s_line.tax.rate if s_line.tax else Decimal('0.00')
                    line_tax = calculate_line_tax(line_subtotal, s_line.tax)

                    desc = s_line.product.name
                    if s_line.variant:
                        desc = f"{s_line.product.name} ({s_line.variant.attribute}: {s_line.variant.value})"

                    InvoiceLine.objects.create(
                        invoice=invoice,
                        description=desc,
                        product=s_line.product,
                        quantity=s_line.quantity,
                        unit_price=s_line.unit_price,
                        tax_rate=tax_rate,
                        tax_amount=line_tax,
                        amount=line_subtotal,
                        is_discount=False,
                    )

                    subtotal += line_subtotal
                    tax_total += line_tax

                # Apply discounts as negative lines
                discounts = get_applicable_discounts(sub, on=today)
                for disc, disc_amount in discounts:
                    InvoiceLine.objects.create(
                        invoice=invoice,
                        description=f"Discount: {disc.name}",
                        product=None,
                        quantity=1,
                        unit_price=-disc_amount,
                        tax_rate=Decimal('0.00'),
                        tax_amount=Decimal('0.00'),
                        amount=-disc_amount,
                        is_discount=True,
                        discount=disc,
                    )
                    discount_total += disc_amount

                    # Increment discount usage count atomically
                    disc.used_count += 1
                    disc.save(update_fields=['used_count'])

                # Compute final invoice total
                final_total = max(Decimal('0.00'), subtotal - discount_total + tax_total)

                invoice.subtotal = subtotal
                invoice.discount_total = discount_total
                invoice.tax_total = tax_total
                invoice.total = final_total
                invoice.save(update_fields=['subtotal', 'discount_total', 'tax_total', 'total'])

                # Advance next_invoice_date by one plan period
                sub.next_invoice_date = add_plan_period(period_start, sub.plan.billing_period)
                sub.save(update_fields=['next_invoice_date'])

                generated.append(invoice)
                total_due += final_total

        except IntegrityError:
            # Caught unique constraint: already invoiced for this period
            skipped.append({
                'subscription': sub,
                'message': f"Duplicate prevented: period {period_start} to {period_end} is already invoiced.",
            })

    # Save BillingRun audit record
    billing_run = BillingRun.objects.create(
        run_by=user,
        is_preview=False,
        total_due=total_due,
        generated=len(generated),
        skipped=len(skipped),
        flagged=len(flagged),
    )

    # Save Review Queue BillingFlag records for staff attention
    for item in flagged:
        BillingFlag.objects.create(
            run=billing_run,
            subscription=item['subscription'],
            reason=item['reason'],
            message=item['message'],
        )

    return {
        'run': billing_run,
        'ready': [],
        'generated': generated,
        'skipped': skipped,
        'flagged': flagged,
    }
