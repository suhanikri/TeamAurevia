from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from django.db.models import Sum, Count, F, Q, DecimalField
from django.utils import timezone

from catalog.models import Plan
from subscriptions.models import Subscription, SubscriptionLine
from billing.models import Invoice, Payment, BillingFlag


def calculate_mrr(active_subs_qs=None):
    """
    Computes Monthly Recurring Revenue (MRR) across all active subscriptions:
    - Daily: sum * 30
    - Weekly: sum * 52 / 12
    - Monthly: sum * 1
    - Yearly: sum / 12
    """
    lines_qs = SubscriptionLine.objects.filter(subscription__status=Subscription.STATUS_ACTIVE)
    if active_subs_qs is not None:
        lines_qs = lines_qs.filter(subscription__in=active_subs_qs)

    period_totals = lines_qs.values('subscription__plan__billing_period').annotate(
        total_rev=Sum(F('quantity') * F('unit_price'), output_field=DecimalField(max_digits=14, decimal_places=2))
    )

    totals_by_period = {
        Plan.PERIOD_DAILY: Decimal('0.00'),
        Plan.PERIOD_WEEKLY: Decimal('0.00'),
        Plan.PERIOD_MONTHLY: Decimal('0.00'),
        Plan.PERIOD_YEARLY: Decimal('0.00'),
    }

    mrr = Decimal('0.00')
    for pt in period_totals:
        period = pt['subscription__plan__billing_period']
        amount = pt['total_rev'] or Decimal('0.00')

        if period == Plan.PERIOD_DAILY:
            converted = (amount * Decimal('30')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        elif period == Plan.PERIOD_WEEKLY:
            converted = (amount * Decimal('52') / Decimal('12')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        elif period == Plan.PERIOD_MONTHLY:
            converted = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        elif period == Plan.PERIOD_YEARLY:
            converted = (amount / Decimal('12')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            converted = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        totals_by_period[period] = converted
        mrr += converted

    return mrr, totals_by_period


def get_dashboard_metrics(today=None, start_date=None, end_date=None, plan_id=None, status_filter=None):
    """
    Returns dashboard summary KPIs, charts, and table lists using efficient DB queries.
    """
    if today is None:
        today = timezone.now().date()

    # 1. Base Subscription Query with filters
    subs_qs = Subscription.objects.all()
    if plan_id:
        subs_qs = subs_qs.filter(plan_id=plan_id)
    if status_filter:
        subs_qs = subs_qs.filter(status=status_filter)

    active_subs_count = subs_qs.filter(status=Subscription.STATUS_ACTIVE).count()
    total_mrr, mrr_by_period = calculate_mrr(active_subs_qs=subs_qs.filter(status=Subscription.STATUS_ACTIVE))

    # 2. Payments (Revenue collected in date range)
    payments_qs = Payment.objects.all()
    if start_date:
        payments_qs = payments_qs.filter(payment_date__gte=start_date)
    if end_date:
        payments_qs = payments_qs.filter(payment_date__lte=end_date)
    if plan_id:
        payments_qs = payments_qs.filter(invoice__subscription__plan_id=plan_id)

    revenue_collected = payments_qs.aggregate(sum=Sum('amount'))['sum'] or Decimal('0.00')

    # 3. Invoices (Outstanding and Overdue)
    inv_qs = Invoice.objects.exclude(status=Invoice.STATUS_CANCELLED)
    if plan_id:
        inv_qs = inv_qs.filter(subscription__plan_id=plan_id)

    confirmed_invs = inv_qs.filter(status=Invoice.STATUS_CONFIRMED).annotate(
        rem_balance=F('total') - F('amount_paid')
    )

    total_outstanding = confirmed_invs.aggregate(sum=Sum('rem_balance'))['sum'] or Decimal('0.00')

    overdue_qs = confirmed_invs.filter(due_date__lt=today, rem_balance__gt=0)
    overdue_agg = overdue_qs.aggregate(count=Count('id'), sum=Sum('rem_balance'))
    count_overdue = overdue_agg['count'] or 0
    total_overdue = overdue_agg['sum'] or Decimal('0.00')

    # 4. Revenue at Risk: Overdue balance + Subtotal of active subscriptions with unresolved billing flags
    unresolved_flags = BillingFlag.objects.filter(
        resolved=False,
        subscription__status=Subscription.STATUS_ACTIVE,
    )
    if plan_id:
        unresolved_flags = unresolved_flags.filter(subscription__plan_id=plan_id)

    flagged_sub_ids = unresolved_flags.values_list('subscription_id', flat=True).distinct()
    unresolved_flags_count = unresolved_flags.count()

    flagged_subs_subtotal = SubscriptionLine.objects.filter(
        subscription_id__in=flagged_sub_ids
    ).annotate(
        line_total=F('quantity') * F('unit_price')
    ).aggregate(sum=Sum('line_total'))['sum'] or Decimal('0.00')

    revenue_at_risk = total_overdue + flagged_subs_subtotal

    # 5. Tables: Top 10 Overdue Invoices
    top_overdue = overdue_qs.select_related('customer', 'subscription').order_by('due_date')[:10]
    top_overdue_list = []
    for inv in top_overdue:
        days = (today - inv.due_date).days if inv.due_date else 0
        top_overdue_list.append({
            'invoice': inv,
            'days_overdue': days,
            'balance': inv.balance,
        })

    # 6. Upcoming Renewals (next 30 days)
    upcoming_renewals = subs_qs.filter(
        status=Subscription.STATUS_ACTIVE,
        next_invoice_date__gte=today,
        next_invoice_date__lte=today + timedelta(days=30),
    ).select_related('customer', 'plan').order_by('next_invoice_date')[:10]

    # 7. Chart.js Data
    # 7a. Invoice Status Breakdown
    status_counts = inv_qs.values('status').annotate(c=Count('id'))
    status_dict = {item['status']: item['c'] for item in status_counts}
    status_chart_data = {
        'labels': ['Paid', 'Confirmed', 'Draft', 'Cancelled'],
        'values': [
            status_dict.get(Invoice.STATUS_PAID, 0),
            status_dict.get(Invoice.STATUS_CONFIRMED, 0),
            status_dict.get(Invoice.STATUS_DRAFT, 0),
            Invoice.objects.filter(status=Invoice.STATUS_CANCELLED).count(),
        ]
    }

    # 7b. MRR by Billing Period
    mrr_chart_data = {
        'labels': ['Monthly', 'Yearly', 'Weekly', 'Daily'],
        'values': [
            float(mrr_by_period.get(Plan.PERIOD_MONTHLY, 0)),
            float(mrr_by_period.get(Plan.PERIOD_YEARLY, 0)),
            float(mrr_by_period.get(Plan.PERIOD_WEEKLY, 0)),
            float(mrr_by_period.get(Plan.PERIOD_DAILY, 0)),
        ]
    }

    # 7c. Monthly Revenue Trend (Last 6 Months)
    monthly_trend_labels = []
    monthly_trend_values = []
    for i in range(5, -1, -1):
        m_start = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        next_m = (m_start + timedelta(days=32)).replace(day=1)
        rev = Payment.objects.filter(payment_date__gte=m_start, payment_date__lt=next_m).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        monthly_trend_labels.append(m_start.strftime('%b %Y'))
        monthly_trend_values.append(float(rev))

    revenue_chart_data = {
        'labels': monthly_trend_labels,
        'values': monthly_trend_values,
    }

    return {
        'active_subs_count': active_subs_count,
        'total_mrr': total_mrr,
        'revenue_collected': revenue_collected,
        'total_outstanding': total_outstanding,
        'count_overdue': count_overdue,
        'total_overdue': total_overdue,
        'revenue_at_risk': revenue_at_risk,
        'unresolved_flags_count': unresolved_flags_count,
        'top_overdue_list': top_overdue_list,
        'upcoming_renewals': upcoming_renewals,
        'status_chart_data': status_chart_data,
        'mrr_chart_data': mrr_chart_data,
        'revenue_chart_data': revenue_chart_data,
    }


def get_plan_summary_data():
    """
    Computes summary metrics grouped by Plan:
    Active subscriptions, MRR, Invoiced, Collected, Outstanding.
    """
    plans = Plan.objects.all().order_by('name')
    summary_list = []

    for plan in plans:
        # Active subs
        active_subs = Subscription.objects.filter(plan=plan, status=Subscription.STATUS_ACTIVE)
        active_count = active_subs.count()

        # MRR for this plan
        plan_mrr, _ = calculate_mrr(active_subs_qs=active_subs)

        # Invoices for this plan
        plan_invs = Invoice.objects.filter(subscription__plan=plan).exclude(status=Invoice.STATUS_CANCELLED)
        inv_agg = plan_invs.aggregate(
            invoiced=Sum('total'),
            collected=Sum('amount_paid'),
        )
        invoiced = inv_agg['invoiced'] or Decimal('0.00')
        collected = inv_agg['collected'] or Decimal('0.00')
        outstanding = max(Decimal('0.00'), invoiced - collected)

        summary_list.append({
            'plan': plan,
            'active_count': active_count,
            'mrr': plan_mrr,
            'invoiced': invoiced,
            'collected': collected,
            'outstanding': outstanding,
        })

    return summary_list

