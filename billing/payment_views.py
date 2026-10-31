from decimal import Decimal
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F, Case, When, DecimalField
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from accounts.permissions import staff_or_admin
from .models import Invoice, Payment
from .payments import record_payment


class PaymentRecordForm(forms.Form):
    method = forms.ChoiceField(
        choices=Payment.METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Payment Method",
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label="Amount to Pay ($)",
    )
    payment_date = forms.DateField(
        initial=timezone.now,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="Payment Date",
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional transaction reference / notes'}),
        label="Note / Reference",
    )


@staff_or_admin
def record_invoice_payment(request, invoice_id):
    """
    Record a payment against a specific invoice.
    """
    invoice = get_object_or_404(Invoice.objects.select_related('customer', 'subscription'), pk=invoice_id)

    if invoice.status != Invoice.STATUS_CONFIRMED:
        messages.warning(
            request,
            f"Payments can only be added to Confirmed invoices. Invoice {invoice.number} is '{invoice.get_status_display()}'."
        )

    initial_data = {
        'amount': invoice.balance if invoice.balance > Decimal('0.00') else Decimal('0.00'),
        'payment_date': timezone.now().date(),
    }
    form = PaymentRecordForm(request.POST or None, initial=initial_data)

    if request.method == 'POST' and form.is_valid():
        try:
            payment = record_payment(
                invoice=invoice,
                method=form.cleaned_data['method'],
                amount=form.cleaned_data['amount'],
                payment_date=form.cleaned_data['payment_date'],
                note=form.cleaned_data['note'],
                user=request.user,
            )
            messages.success(
                request,
                f"Payment of ${payment.amount} recorded for {invoice.number}. Status is now '{invoice.get_status_display()}'."
            )
            # Try redirecting to invoice detail if route exists, else fallback to payments list
            try:
                return redirect(f"/invoices/{invoice.pk}/")
            except Exception:
                return redirect('payments:list')
        except ValidationError as e:
            form.add_error(None, e.message if hasattr(e, 'message') else str(e))

    return render(request, 'payments/record_payment.html', {
        'invoice': invoice,
        'form': form,
    })


@staff_or_admin
def payment_list(request):
    """
    Paginated list of all recorded payments with filters and total collected counter.
    """
    qs = Payment.objects.select_related('invoice', 'invoice__customer', 'recorded_by').order_by('-payment_date', '-id')

    # Filter by payment method
    method_filter = request.GET.get('method', '').strip()
    if method_filter:
        qs = qs.filter(method=method_filter)

    # Filter by date range
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    if start_date:
        qs = qs.filter(payment_date__gte=start_date)
    if end_date:
        qs = qs.filter(payment_date__lte=end_date)

    # Search by invoice number or customer email
    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(invoice__number__icontains=query) |
            Q(invoice__customer__email__icontains=query) |
            Q(note__icontains=query)
        )

    # Total collected across current filtered set
    total_collected = qs.aggregate(sum=Sum('amount'))['sum'] or Decimal('0.00')

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'payments/payment_list.html', {
        'page_obj': page_obj,
        'total_collected': total_collected,
        'method_choices': Payment.METHOD_CHOICES,
        'selected_method': method_filter,
        'start_date': start_date,
        'end_date': end_date,
        'query': query,
    })


@staff_or_admin
def paid_vs_outstanding(request):
    """
    Paid vs Outstanding dashboard view with status tabs and aggregate summary cards.
    """
    today = timezone.now().date()
    tab = request.GET.get('tab', 'all').strip().lower()

    base_qs = Invoice.objects.exclude(status=Invoice.STATUS_CANCELLED).select_related('customer', 'subscription')

    # High-level aggregate KPIs
    agg = base_qs.aggregate(
        total_invoiced=Sum('total'),
        total_collected=Sum('amount_paid'),
    )
    total_invoiced = agg['total_invoiced'] or Decimal('0.00')
    total_collected = agg['total_collected'] or Decimal('0.00')

    # Outstanding invoices (confirmed status)
    confirmed_invoices = base_qs.filter(status=Invoice.STATUS_CONFIRMED)
    outstanding_agg = confirmed_invoices.annotate(
        rem_balance=F('total') - F('amount_paid')
    ).aggregate(sum=Sum('rem_balance'))
    total_outstanding = outstanding_agg['sum'] or Decimal('0.00')

    # Overdue invoices (confirmed and due_date < today)
    overdue_invoices = confirmed_invoices.filter(due_date__lt=today).annotate(
        rem_balance=F('total') - F('amount_paid')
    ).filter(rem_balance__gt=0)

    overdue_agg = overdue_invoices.aggregate(
        sum=Sum('rem_balance')
    )
    total_overdue = overdue_agg['sum'] or Decimal('0.00')
    count_overdue = overdue_invoices.count()

    # Filter according to selected tab
    if tab == 'paid':
        qs = base_qs.filter(status=Invoice.STATUS_PAID)
    elif tab == 'outstanding':
        qs = confirmed_invoices.annotate(
            rem_balance=F('total') - F('amount_paid')
        ).filter(rem_balance__gt=0)
    elif tab == 'overdue':
        qs = overdue_invoices
    else:
        qs = base_qs

    # Search filter
    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(number__icontains=query) |
            Q(customer__email__icontains=query)
        )

    qs = qs.order_by('-invoice_date', '-id')

    # Annotate days overdue in python/template
    invoices_list = []
    for inv in qs:
        days_overdue = 0
        if inv.status == Invoice.STATUS_CONFIRMED and inv.due_date and inv.due_date < today and inv.balance > 0:
            days_overdue = (today - inv.due_date).days
        invoices_list.append({
            'invoice': inv,
            'days_overdue': days_overdue,
        })

    paginator = Paginator(invoices_list, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'payments/outstanding.html', {
        'page_obj': page_obj,
        'tab': tab,
        'query': query,
        'total_invoiced': total_invoiced,
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,
        'total_overdue': total_overdue,
        'count_overdue': count_overdue,
    })

