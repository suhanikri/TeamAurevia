from datetime import datetime
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import staff_or_admin
from billing.models import BillingFlag, BillingRun


def get_billing_engine():
    """Lazily import the billing integrity engine to prevent crashes if not present."""
    try:
        from billing import engine
        return engine
    except ImportError:
        return None


@staff_or_admin
def billing_home(request):
    """
    Billing Run Home dashboard:
    - Big 'Preview Billing' action.
    - Summary of unresolved review queue flags.
    - Historical table of recent BillingRun records.
    """
    recent_runs = BillingRun.objects.select_related('run_by').order_by('-run_at')[:20]
    unresolved_flags_count = BillingFlag.objects.filter(resolved=False).count()
    today_str = timezone.now().date().isoformat()

    return render(request, 'billing/home.html', {
        'recent_runs': recent_runs,
        'unresolved_flags_count': unresolved_flags_count,
        'today_str': today_str,
    })


@staff_or_admin
@require_POST
def billing_preview(request):
    """
    Executes preview_billing for the specified date (defaults to today).
    Displays summary cards (ready, skipped, flagged) and details tables.
    """
    engine = get_billing_engine()
    date_str = request.POST.get('target_date', '').strip()
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = timezone.now().date()
    else:
        target_date = timezone.now().date()

    if not engine:
        messages.warning(request, "Billing Engine is not installed yet. Displaying sample preview.")
        preview_data = {
            'run': None,
            'ready': [],
            'generated': [],
            'skipped': [],
            'flagged': [],
        }
    else:
        preview_data = engine.preview_billing(today=target_date)

    ready_subs = preview_data.get('ready', [])
    skipped_items = preview_data.get('skipped', [])
    flagged_items = preview_data.get('flagged', [])

    # Calculate potential total due for ready subscriptions
    potential_total = sum((sub.total for sub in ready_subs), Decimal('0.00'))

    return render(request, 'billing/preview.html', {
        'target_date': target_date,
        'ready_subs': ready_subs,
        'skipped_items': skipped_items,
        'flagged_items': flagged_items,
        'potential_total': potential_total,
    })


@staff_or_admin
@require_POST
def billing_run_action(request):
    """
    Executes run_billing for ready subscriptions.
    Generates draft invoices, increments discounts, flags issues, and displays run report.
    """
    engine = get_billing_engine()
    date_str = request.POST.get('target_date', '').strip()
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = timezone.now().date()
    else:
        target_date = timezone.now().date()

    if not engine:
        messages.error(request, "Billing Engine is not available.")
        return redirect('billing_run:home')

    result = engine.run_billing(today=target_date, user=request.user)

    billing_run = result.get('run')
    generated_invoices = result.get('generated', [])
    skipped_items = result.get('skipped', [])
    flagged_items = result.get('flagged', [])

    messages.success(
        request,
        f"Billing Run completed! {len(generated_invoices)} invoices generated, "
        f"{len(skipped_items)} skipped, {len(flagged_items)} flagged for review."
    )

    return render(request, 'billing/run_report.html', {
        'billing_run': billing_run,
        'generated_invoices': generated_invoices,
        'skipped_items': skipped_items,
        'flagged_items': flagged_items,
        'target_date': target_date,
    })


@staff_or_admin
def review_queue(request):
    """
    Review Queue for unresolved and resolved BillingFlag records.
    Admin and staff only.
    """
    filter_status = request.GET.get('status', 'unresolved').strip().lower()

    qs = (
        BillingFlag.objects
        .select_related('subscription__customer', 'subscription__plan', 'run')
        .order_by('-created_at')
    )

    if filter_status == 'resolved':
        qs = qs.filter(resolved=True)
    elif filter_status == 'all':
        pass
    else:
        qs = qs.filter(resolved=False)

    unresolved_count = BillingFlag.objects.filter(resolved=False).count()
    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'billing/review_queue.html', {
        'page_obj': page_obj,
        'filter_status': filter_status,
        'unresolved_count': unresolved_count,
    })


@staff_or_admin
@require_POST
def resolve_flag(request, flag_id):
    """
    Marks a BillingFlag as resolved.
    """
    flag = get_object_or_404(BillingFlag, id=flag_id)
    flag.resolved = True
    flag.save(update_fields=['resolved'])
    messages.success(
        request,
        f"Flag on subscription {flag.subscription.number or flag.subscription.id} marked as resolved."
    )
    return redirect('billing_run:review')
