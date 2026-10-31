import csv
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.permissions import staff_or_admin
from catalog.models import Plan
from subscriptions.models import Subscription
from .services import get_dashboard_metrics, get_plan_summary_data


@staff_or_admin
def dashboard(request):
    """
    Finance Lead Executive Dashboard:
    - Active Subscriptions, MRR, Collected, Outstanding, Overdue, Revenue at Risk.
    - Top 10 Overdue Invoices.
    - Upcoming Contract Renewals.
    - Interactive Chart.js Visualizations.
    """
    today = timezone.now().date()

    # Filters
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    plan_id = request.GET.get('plan', '').strip()
    status_filter = request.GET.get('status', '').strip()

    metrics = get_dashboard_metrics(
        today=today,
        start_date=start_date or None,
        end_date=end_date or None,
        plan_id=int(plan_id) if plan_id and plan_id.isdigit() else None,
        status_filter=status_filter or None,
    )

    plans = Plan.objects.filter(is_active=True).order_by('name')

    context = {
        **metrics,
        'today': today,
        'plans': plans,
        'status_choices': Subscription.STATUS_CHOICES,
        'selected_start_date': start_date,
        'selected_end_date': end_date,
        'selected_plan': int(plan_id) if plan_id and plan_id.isdigit() else '',
        'selected_status': status_filter,
    }

    return render(request, 'reports/dashboard.html', context)


@staff_or_admin
def summary_report(request):
    """
    Plan-level revenue summary report with CSV export.
    """
    summary_data = get_plan_summary_data()

    # CSV Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="subsentry_plan_summary_{timezone.now():%Y%m%d}.csv"'

        writer = csv.writer(response)
        writer.writerow(['Plan Name', 'Billing Period', 'Active Subscriptions', 'MRR (₹)', 'Total Invoiced (₹)', 'Total Collected (₹)', 'Total Outstanding (₹)'])

        for row in summary_data:
            writer.writerow([
                row['plan'].name,
                row['plan'].get_billing_period_display(),
                row['active_count'],
                f"{row['mrr']:.2f}",
                f"{row['invoiced']:.2f}",
                f"{row['collected']:.2f}",
                f"{row['outstanding']:.2f}",
            ])

        return response

    return render(request, 'reports/summary.html', {
        'summary_data': summary_data,
    })
