from decimal import Decimal
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import staff_or_admin, any_logged_in_role
from .forms import CreateFromTemplateForm, ManualSubscriptionForm, SubscriptionLineFormSet
from .models import Subscription, SubscriptionLine
from .services import create_subscription_from_template, add_plan_period


@any_logged_in_role
def subscription_list(request):
    """
    List subscriptions with status filter, search, and pagination (25/page).
    Customers see only their own subscriptions.
    Staff and Admin see all subscriptions.
    """
    is_staff = getattr(request.user, 'role', None) in ('admin', 'staff')
    if is_staff:
        qs = Subscription.objects.all()
    else:
        qs = Subscription.objects.filter(customer=request.user)

    qs = qs.select_related('customer', 'plan', 'template').prefetch_related('lines', 'lines__tax')

    # Filter by status
    status_filter = request.GET.get('status', '').strip().lower()
    if status_filter in dict(Subscription.STATUS_CHOICES):
        qs = qs.filter(status=status_filter)

    # Search by number or customer email
    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(number__icontains=query) |
            Q(customer__email__icontains=query)
        )

    qs = qs.order_by('-created_at')

    # Paginate 25 items per page
    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'subscriptions/subscription_list.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'status_choices': Subscription.STATUS_CHOICES,
        'query': query,
        'is_staff': is_staff,
    })


@any_logged_in_role
def subscription_detail(request, pk):
    """
    Detail page for a subscription with lines, totals, and allowed action buttons.
    Customers cannot view other customers' subscriptions (returns 404).
    """
    is_staff = getattr(request.user, 'role', None) in ('admin', 'staff')
    subscription = get_object_or_404(
        Subscription.objects.select_related('customer', 'plan', 'template', 'discount', 'created_by')
        .prefetch_related('lines', 'lines__product', 'lines__variant', 'lines__tax'),
        pk=pk,
    )

    if not is_staff and subscription.customer != request.user:
        raise Http404("Subscription not found.")

    lines = subscription.lines.all()
    subtotal = subscription.subtotal
    tax_total = subscription.tax_total
    total = subscription.total

    return render(request, 'subscriptions/subscription_detail.html', {
        'subscription': subscription,
        'lines': lines,
        'subtotal': subtotal,
        'tax_total': tax_total,
        'total': total,
        'is_staff': is_staff,
    })


@staff_or_admin
def subscription_create_from_template(request):
    """
    Create a new subscription from a quotation template.
    """
    form = CreateFromTemplateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        customer = form.cleaned_data['customer']
        template = form.cleaned_data['template']
        start_date = form.cleaned_data['start_date']
        payment_terms_days = form.cleaned_data['payment_terms_days']

        subscription = create_subscription_from_template(
            customer=customer,
            template=template,
            start_date=start_date,
            payment_terms_days=payment_terms_days,
            created_by=request.user,
        )

        messages.success(request, f"Subscription {subscription.number} created from template '{template.name}'.")
        return redirect('subscriptions:detail', pk=subscription.pk)

    return render(request, 'subscriptions/subscription_create_template.html', {
        'form': form,
    })


@staff_or_admin
def subscription_create_manual(request):
    """
    Create a new subscription manually with inline product lines.
    """
    form = ManualSubscriptionForm(request.POST or None)
    formset = SubscriptionLineFormSet(request.POST or None)

    if request.method == 'POST':
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                subscription = form.save(commit=False)
                subscription.created_by = request.user
                if not subscription.expiry_date and subscription.plan:
                    subscription.expiry_date = add_plan_period(subscription.start_date, subscription.plan.billing_period)
                subscription.next_invoice_date = subscription.start_date
                subscription.save()

                formset.instance = subscription
                formset.save()

            messages.success(request, f"Subscription {subscription.number} created successfully.")
            return redirect('subscriptions:detail', pk=subscription.pk)

    return render(request, 'subscriptions/subscription_create_manual.html', {
        'form': form,
        'formset': formset,
    })


@staff_or_admin
@require_POST
def subscription_action(request, pk, action):
    """
    Execute status transitions with plan flags enforcement:
    - quotation: Draft -> Quotation
    - confirm: Quotation/Draft -> Confirmed
    - activate: Confirmed/Draft/Quotation -> Active
    - pause: Active -> Paused (checks plan.is_pausable)
    - resume: Paused -> Active
    - close: -> Closed (checks plan.is_closable)
    - renew: extends expiry_date (checks plan.is_renewable)
    """
    subscription = get_object_or_404(
        Subscription.objects.select_related('plan'),
        pk=pk,
    )
    plan = subscription.plan

    if action == 'quotation':
        if subscription.status == Subscription.STATUS_DRAFT:
            subscription.status = Subscription.STATUS_QUOTATION
            subscription.save(update_fields=['status'])
            messages.success(request, f"{subscription.number} marked as Quotation.")
        else:
            messages.error(request, f"Cannot convert {subscription.get_status_display()} to Quotation.")

    elif action == 'confirm':
        if subscription.status in (Subscription.STATUS_DRAFT, Subscription.STATUS_QUOTATION):
            subscription.status = Subscription.STATUS_CONFIRMED
            subscription.save(update_fields=['status'])
            messages.success(request, f"{subscription.number} confirmed.")
        else:
            messages.error(request, f"Cannot confirm subscription from status {subscription.get_status_display()}.")

    elif action == 'activate':
        if subscription.status in (Subscription.STATUS_DRAFT, Subscription.STATUS_QUOTATION, Subscription.STATUS_CONFIRMED):
            subscription.status = Subscription.STATUS_ACTIVE
            update_fields = ['status']
            if not subscription.next_invoice_date:
                subscription.next_invoice_date = subscription.start_date
                update_fields.append('next_invoice_date')
            subscription.save(update_fields=update_fields)
            messages.success(request, f"{subscription.number} is now Active.")
        else:
            messages.error(request, f"Cannot activate subscription from status {subscription.get_status_display()}.")

    elif action == 'pause':
        if subscription.status != Subscription.STATUS_ACTIVE:
            messages.error(request, "Only Active subscriptions can be paused.")
        elif not plan.is_pausable:
            messages.error(request, f"Plan '{plan.name}' does not allow pausing.")
        else:
            subscription.status = Subscription.STATUS_PAUSED
            subscription.save(update_fields=['status'])
            messages.success(request, f"{subscription.number} has been paused.")

    elif action == 'resume':
        if subscription.status == Subscription.STATUS_PAUSED:
            subscription.status = Subscription.STATUS_ACTIVE
            subscription.save(update_fields=['status'])
            messages.success(request, f"{subscription.number} has been resumed and is now Active.")
        else:
            messages.error(request, "Only Paused subscriptions can be resumed.")

    elif action == 'close':
        if subscription.status == Subscription.STATUS_CLOSED:
            messages.info(request, "Subscription is already closed.")
        elif subscription.status in (Subscription.STATUS_ACTIVE, Subscription.STATUS_PAUSED) and not plan.is_closable:
            messages.error(request, f"Plan '{plan.name}' does not permit early closure.")
        else:
            subscription.status = Subscription.STATUS_CLOSED
            subscription.save(update_fields=['status'])
            messages.success(request, f"{subscription.number} has been closed.")

    elif action == 'renew':
        if not plan.is_renewable:
            messages.error(request, f"Plan '{plan.name}' does not permit renewals.")
        else:
            base_date = subscription.expiry_date or timezone.now().date()
            subscription.expiry_date = add_plan_period(base_date, plan.billing_period)
            update_fields = ['expiry_date']
            if subscription.status == Subscription.STATUS_CLOSED:
                subscription.status = Subscription.STATUS_ACTIVE
                update_fields.append('status')
            subscription.save(update_fields=update_fields)
            messages.success(request, f"{subscription.number} renewed successfully until {subscription.expiry_date}.")

    else:
        messages.error(request, f"Unknown action '{action}'.")

    return redirect('subscriptions:detail', pk=subscription.pk)
