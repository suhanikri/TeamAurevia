from functools import wraps
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from billing.models import Invoice, Payment
from subscriptions.models import Subscription


def customer_required(view_func):
    """
    Decorator for Customer Portal views:
    - Redirects anonymous users to login.
    - Redirects admin and staff users to /dashboard/.
    - Only allows users with role == 'customer'.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        role = getattr(request.user, 'role', None)
        if role in ('admin', 'staff'):
            return redirect('/dashboard/')
        if role != 'customer':
            raise PermissionDenied("Customer access only.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@customer_required
def subscription_list(request):
    """
    List of subscriptions belonging ONLY to the logged-in customer.
    Paginated (25 per page).
    """
    qs = (
        Subscription.objects
        .filter(customer=request.user)
        .select_related('plan')
        .prefetch_related('lines')
        .order_by('-id')
    )
    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'portal/subscription_list.html', {
        'page_obj': page_obj,
    })


@customer_required
def subscription_detail(request, id):
    """
    Detail of a single subscription belonging to the logged-in customer.
    Shows plan info, lines, taxes, totals, and linked invoices.
    Returns 404 if subscription belongs to another customer.
    """
    subscription = get_object_or_404(
        Subscription.objects
        .select_related('plan', 'discount')
        .prefetch_related(
            'lines__product',
            'lines__variant',
            'lines__tax',
            'invoices',
        ),
        id=id,
        customer=request.user,
    )
    invoices = subscription.invoices.all().order_by('-invoice_date', '-id')

    return render(request, 'portal/subscription_detail.html', {
        'subscription': subscription,
        'invoices': invoices,
    })


@customer_required
def invoice_list(request):
    """
    List of invoices belonging ONLY to the logged-in customer.
    Supports filtering by status (including 'overdue').
    Paginated (25 per page).
    """
    status_filter = request.GET.get('status', '').strip().lower()
    qs = (
        Invoice.objects
        .filter(customer=request.user)
        .select_related('subscription')
        .order_by('-invoice_date', '-id')
    )

    if status_filter == 'overdue':
        today = timezone.now().date()
        qs = qs.filter(
            status=Invoice.STATUS_CONFIRMED,
            due_date__lt=today,
            total__gt=F('amount_paid'),
        )
    elif status_filter in dict(Invoice.STATUS_CHOICES):
        qs = qs.filter(status=status_filter)

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'portal/invoice_list.html', {
        'page_obj': page_obj,
        'current_status': status_filter,
    })


@customer_required
def invoice_detail(request, id):
    """
    Detail view of an invoice for the logged-in customer.
    Shows lines (discounts green/negative), tax, total, payments made,
    and a Print button for print-friendly layout.
    Returns 404 if invoice belongs to another customer.
    """
    invoice = get_object_or_404(
        Invoice.objects
        .select_related('subscription', 'customer')
        .prefetch_related('lines__product', 'payments'),
        id=id,
        customer=request.user,
    )
    payments = invoice.payments.all().order_by('-payment_date', '-id')

    return render(request, 'portal/invoice_detail.html', {
        'invoice': invoice,
        'payments': payments,
    })


@customer_required
def payment_list(request):
    """
    Payment history for the logged-in customer.
    Paginated (25 per page).
    """
    qs = (
        Payment.objects
        .filter(invoice__customer=request.user)
        .select_related('invoice')
        .order_by('-payment_date', '-id')
    )
    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'portal/payment_list.html', {
        'page_obj': page_obj,
    })
