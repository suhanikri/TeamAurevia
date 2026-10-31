from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import staff_or_admin
from billing.models import Invoice


@staff_or_admin
def invoice_list(request):
    """
    Staff/Admin list of all invoices with pagination, filtering, and search.
    Filters: status, overdue only, search (invoice number or customer email), date range.
    """
    status_filter = request.GET.get('status', '').strip().lower()
    overdue_only = request.GET.get('overdue') in ('true', '1', 'on')
    search_query = request.GET.get('search', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    qs = (
        Invoice.objects
        .select_related('customer', 'subscription')
        .order_by('-invoice_date', '-id')
    )

    today = timezone.now().date()

    if overdue_only:
        qs = qs.filter(
            status=Invoice.STATUS_CONFIRMED,
            due_date__lt=today,
            total__gt=F('amount_paid'),
        )
    elif status_filter in dict(Invoice.STATUS_CHOICES):
        qs = qs.filter(status=status_filter)

    if search_query:
        qs = qs.filter(
            Q(number__icontains=search_query) |
            Q(customer__email__icontains=search_query)
        )

    if date_from:
        qs = qs.filter(invoice_date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice_date__lte=date_to)

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'invoices/invoice_list.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'overdue_only': overdue_only,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
    })


@staff_or_admin
def invoice_detail(request, id):
    """
    Staff/Admin invoice detail view with line items, payments, customer details,
    totals, and lifecycle action controls (Confirm, Cancel, Send, Print, Record Payment).
    """
    invoice = get_object_or_404(
        Invoice.objects
        .select_related('customer', 'subscription')
        .prefetch_related('lines__product', 'payments__recorded_by'),
        id=id,
    )
    payments = invoice.payments.all().order_by('-payment_date', '-id')

    return render(request, 'invoices/invoice_detail.html', {
        'invoice': invoice,
        'payments': payments,
    })


@staff_or_admin
@require_POST
def invoice_confirm(request, id):
    """
    Transition invoice from Draft -> Confirmed.
    """
    invoice = get_object_or_404(Invoice, id=id)

    if invoice.status != Invoice.STATUS_DRAFT:
        messages.error(
            request,
            f"Cannot confirm invoice {invoice.number or invoice.id}: status is already '{invoice.get_status_display()}'."
        )
        return redirect('invoices:detail', id=invoice.id)

    invoice.status = Invoice.STATUS_CONFIRMED
    invoice.save(update_fields=['status'])
    messages.success(request, f"Invoice {invoice.number} confirmed successfully.")
    return redirect('invoices:detail', id=invoice.id)


@staff_or_admin
@require_POST
def invoice_cancel(request, id):
    """
    Transition invoice from Draft or Confirmed -> Cancelled.
    Refuses cancellation if payments exist against the invoice.
    """
    invoice = get_object_or_404(Invoice, id=id)

    if invoice.payments.exists() or (invoice.amount_paid and invoice.amount_paid > Decimal('0.00')):
        messages.error(
            request,
            f"Cannot cancel invoice {invoice.number or invoice.id} because payments have already been recorded against it."
        )
        return redirect('invoices:detail', id=invoice.id)

    if invoice.status not in (Invoice.STATUS_DRAFT, Invoice.STATUS_CONFIRMED):
        messages.error(
            request,
            f"Cannot cancel invoice {invoice.number or invoice.id}: current status is '{invoice.get_status_display()}'."
        )
        return redirect('invoices:detail', id=invoice.id)

    invoice.status = Invoice.STATUS_CANCELLED
    invoice.save(update_fields=['status'])
    messages.success(request, f"Invoice {invoice.number} has been cancelled.")
    return redirect('invoices:detail', id=invoice.id)


@staff_or_admin
@require_POST
def invoice_send(request, id):
    """
    Send invoice notification email to customer using Django's send_mail.
    Only valid for Confirmed or Paid invoices.
    Sets sent_at timestamp to now.
    """
    invoice = get_object_or_404(Invoice.objects.select_related('customer'), id=id)

    if invoice.status not in (Invoice.STATUS_CONFIRMED, Invoice.STATUS_PAID):
        messages.error(
            request,
            f"Cannot send invoice {invoice.number or invoice.id}: only Confirmed or Paid invoices can be sent to customers (status: '{invoice.get_status_display()}')."
        )
        return redirect('invoices:detail', id=invoice.id)

    subject = f"Invoice {invoice.number} from Brightloop Software"
    message_body = (
        f"Dear {invoice.customer.email},\n\n"
        f"Please find your invoice details below:\n"
        f"Invoice Number: {invoice.number}\n"
        f"Invoice Date: {invoice.invoice_date}\n"
        f"Due Date: {invoice.due_date}\n"
        f"Billing Period: {invoice.period_start} to {invoice.period_end}\n"
        f"Total Amount: ₹{invoice.total:,.2f}\n"
        f"Balance Due: ₹{invoice.balance:,.2f}\n\n"
        f"Thank you for choosing Brightloop Software!\n"
    )
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'billing@brightloop.com')

    try:
        send_mail(
            subject=subject,
            message=message_body,
            from_email=from_email,
            recipient_list=[invoice.customer.email],
            fail_silently=False,
        )
        invoice.sent_at = timezone.now()
        invoice.save(update_fields=['sent_at'])
        messages.success(request, f"Invoice {invoice.number} sent to {invoice.customer.email} successfully.")
    except Exception as exc:
        messages.error(request, f"Failed to send email for invoice {invoice.number}: {exc}")

    return redirect('invoices:detail', id=invoice.id)


@staff_or_admin
def invoice_print(request, id):
    """
    Clean print layout with company header 'Brightloop Software', customer details,
    line items, totals, and a PAID or DUE stamp. Optimized for browser printing.
    """
    invoice = get_object_or_404(
        Invoice.objects
        .select_related('customer', 'subscription')
        .prefetch_related('lines__product', 'payments__recorded_by'),
        id=id,
    )
    payments = invoice.payments.all().order_by('-payment_date', '-id')

    return render(request, 'invoices/invoice_print.html', {
        'invoice': invoice,
        'payments': payments,
    })
