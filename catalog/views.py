from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, ProtectedError
from django.urls import reverse

from accounts.permissions import admin_only, staff_or_admin
from .models import Product, ProductVariant, Plan, Tax, Discount, QuotationTemplate, QuotationTemplateLine
from .forms import (
    ProductForm, ProductVariantForm, PlanForm, TaxForm,
    DiscountForm, QuotationTemplateForm, QuotationTemplateLineForm
)


# -----------------------------------------------------------------------------
# Catalog Dashboard
# -----------------------------------------------------------------------------

@staff_or_admin
def catalog_dashboard(request):
    """
    Catalog landing page at /catalog/ with overview cards and quick links.
    """
    context = {
        'products_count': Product.objects.filter(is_active=True).count(),
        'plans_count': Plan.objects.filter(is_active=True).count(),
        'taxes_count': Tax.objects.filter(is_active=True).count(),
        'discounts_count': Discount.objects.filter(is_active=True).count(),
        'templates_count': QuotationTemplate.objects.filter(is_active=True).count(),
    }
    return render(request, 'catalog/dashboard.html', context)


# -----------------------------------------------------------------------------
# Products
# -----------------------------------------------------------------------------

@staff_or_admin
def product_list(request):
    queryset = Product.objects.select_related('tax').prefetch_related('variants').order_by('name')
    
    # Search by name
    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(name__icontains=query)

    # Filter by type
    product_type = request.GET.get('type', '').strip()
    if product_type:
        queryset = queryset.filter(product_type=product_type)

    # Filter by status
    status = request.GET.get('status', 'active').strip()
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
        'product_type': product_type,
        'status': status,
        'product_type_choices': Product.PRODUCT_TYPE_CHOICES,
    }
    return render(request, 'catalog/product_list.html', context)


@admin_only
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save()
            messages.success(request, f"Product '{product.name}' created successfully.")
            return redirect('catalog:product_detail', pk=product.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = ProductForm()
    return render(request, 'catalog/product_form.html', {'form': form, 'title': 'Create Product'})


@staff_or_admin
def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related('tax').prefetch_related('variants'),
        pk=pk
    )
    variant_form = ProductVariantForm()
    return render(request, 'catalog/product_detail.html', {
        'product': product,
        'variant_form': variant_form,
    })


@admin_only
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            product = form.save()
            messages.success(request, f"Product '{product.name}' updated successfully.")
            return redirect('catalog:product_detail', pk=product.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = ProductForm(instance=product)
    return render(request, 'catalog/product_form.html', {
        'form': form,
        'product': product,
        'title': f"Edit Product: {product.name}",
    })


@admin_only
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', 'deactivate')
        if action == 'permanent':
            try:
                name = product.name
                product.delete()
                messages.success(request, f"Product '{name}' permanently deleted.")
                return redirect('catalog:product_list')
            except ProtectedError:
                messages.error(
                    request,
                    f"Cannot delete product '{product.name}' because it is in use by active subscriptions. It has been deactivated instead."
                )
                product.is_active = False
                product.save()
                return redirect('catalog:product_list')
        else:
            product.is_active = False
            product.save()
            messages.success(request, f"Product '{product.name}' deactivated.")
            return redirect('catalog:product_list')

    return render(request, 'catalog/confirm_delete.html', {
        'object': product,
        'title': f"Deactivate / Delete Product: {product.name}",
        'cancel_url': reverse('catalog:product_detail', args=[product.pk]),
    })


@admin_only
def product_variant_add(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductVariantForm(request.POST)
        if form.is_valid():
            variant = form.save(commit=False)
            variant.product = product
            try:
                variant.save()
                messages.success(request, f"Variant '{variant.attribute}: {variant.value}' added (+${variant.extra_price}).")
            except Exception as e:
                messages.error(request, f"Could not add variant: A variant with attribute '{variant.attribute}' and value '{variant.value}' already exists for this product.")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field.title()}: {err}")
    return redirect('catalog:product_detail', pk=pk)


@admin_only
def product_variant_delete(request, pk, variant_pk):
    product = get_object_or_404(Product, pk=pk)
    variant = get_object_or_404(ProductVariant, pk=variant_pk, product=product)
    if request.method == 'POST':
        try:
            name = f"{variant.attribute}: {variant.value}"
            variant.delete()
            messages.success(request, f"Variant '{name}' deleted.")
        except ProtectedError:
            messages.error(request, f"Variant '{variant}' cannot be deleted because it is referenced by existing subscriptions.")
    return redirect('catalog:product_detail', pk=pk)


# -----------------------------------------------------------------------------
# Plans
# -----------------------------------------------------------------------------

@staff_or_admin
def plan_list(request):
    queryset = Plan.objects.order_by('name')

    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(name__icontains=query)

    billing_period = request.GET.get('period', '').strip()
    if billing_period:
        queryset = queryset.filter(billing_period=billing_period)

    status = request.GET.get('status', 'active').strip()
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'catalog/plan_list.html', {
        'page_obj': page_obj,
        'query': query,
        'billing_period': billing_period,
        'status': status,
        'billing_period_choices': Plan.BILLING_PERIOD_CHOICES,
    })


@admin_only
def plan_create(request):
    if request.method == 'POST':
        form = PlanForm(request.POST)
        if form.is_valid():
            plan = form.save()
            messages.success(request, f"Plan '{plan.name}' created successfully.")
            return redirect('catalog:plan_detail', pk=plan.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = PlanForm()
    return render(request, 'catalog/plan_form.html', {'form': form, 'title': 'Create Plan'})


@staff_or_admin
def plan_detail(request, pk):
    plan = get_object_or_404(Plan.objects.prefetch_related('templates'), pk=pk)
    return render(request, 'catalog/plan_detail.html', {'plan': plan})


@admin_only
def plan_update(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    if request.method == 'POST':
        form = PlanForm(request.POST, instance=plan)
        if form.is_valid():
            plan = form.save()
            messages.success(request, f"Plan '{plan.name}' updated successfully.")
            return redirect('catalog:plan_detail', pk=plan.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = PlanForm(instance=plan)
    return render(request, 'catalog/plan_form.html', {
        'form': form,
        'plan': plan,
        'title': f"Edit Plan: {plan.name}",
    })


@admin_only
def plan_delete(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', 'deactivate')
        if action == 'permanent':
            try:
                name = plan.name
                plan.delete()
                messages.success(request, f"Plan '{name}' permanently deleted.")
                return redirect('catalog:plan_list')
            except ProtectedError:
                messages.error(
                    request,
                    f"Cannot delete plan '{plan.name}' because it is in use by active subscriptions. It has been deactivated instead."
                )
                plan.is_active = False
                plan.save()
                return redirect('catalog:plan_list')
        else:
            plan.is_active = False
            plan.save()
            messages.success(request, f"Plan '{plan.name}' deactivated.")
            return redirect('catalog:plan_list')

    return render(request, 'catalog/confirm_delete.html', {
        'object': plan,
        'title': f"Deactivate / Delete Plan: {plan.name}",
        'cancel_url': reverse('catalog:plan_detail', args=[plan.pk]),
    })


@admin_only
def plan_duplicate(request, pk):
    original = get_object_or_404(Plan, pk=pk)
    if request.method == 'POST':
        new_plan = Plan.objects.create(
            name=f"{original.name} (Copy)",
            price=original.price,
            billing_period=original.billing_period,
            min_quantity=original.min_quantity,
            available_from=original.available_from,
            available_to=original.available_to,
            auto_close=original.auto_close,
            is_closable=original.is_closable,
            is_pausable=original.is_pausable,
            is_renewable=original.is_renewable,
            is_active=True,
        )
        messages.success(request, f"Plan duplicated successfully as '{new_plan.name}'.")
        return redirect('catalog:plan_detail', pk=new_plan.pk)
    return redirect('catalog:plan_detail', pk=pk)


# -----------------------------------------------------------------------------
# Taxes
# -----------------------------------------------------------------------------

@staff_or_admin
def tax_list(request):
    queryset = Tax.objects.order_by('-is_active', 'name')

    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(name__icontains=query)

    status = request.GET.get('status', 'active').strip()
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'catalog/tax_list.html', {
        'page_obj': page_obj,
        'query': query,
        'status': status,
    })


@admin_only
def tax_create(request):
    if request.method == 'POST':
        form = TaxForm(request.POST)
        if form.is_valid():
            tax = form.save()
            messages.success(request, f"Tax '{tax.name}' ({tax.rate}%) created successfully.")
            return redirect('catalog:tax_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = TaxForm()
    return render(request, 'catalog/tax_form.html', {'form': form, 'title': 'Create Tax'})


@admin_only
def tax_update(request, pk):
    tax = get_object_or_404(Tax, pk=pk)
    if request.method == 'POST':
        form = TaxForm(request.POST, instance=tax)
        if form.is_valid():
            tax = form.save()
            messages.success(request, f"Tax '{tax.name}' updated successfully.")
            return redirect('catalog:tax_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = TaxForm(instance=tax)
    return render(request, 'catalog/tax_form.html', {
        'form': form,
        'tax': tax,
        'title': f"Edit Tax: {tax.name}",
    })


@admin_only
def tax_delete(request, pk):
    tax = get_object_or_404(Tax, pk=pk)
    if request.method == 'POST':
        tax.is_active = not tax.is_active
        tax.save()
        status_str = "activated" if tax.is_active else "deactivated"
        messages.success(request, f"Tax '{tax.name}' has been {status_str}.")
        return redirect('catalog:tax_list')
    return render(request, 'catalog/confirm_delete.html', {
        'object': tax,
        'title': f"Toggle Tax Status: {tax.name}",
        'cancel_url': reverse('catalog:tax_list'),
    })


# -----------------------------------------------------------------------------
# Discounts (Admin only for CUD, Staff view list/detail)
# -----------------------------------------------------------------------------

@staff_or_admin
def discount_list(request):
    queryset = Discount.objects.prefetch_related('products').order_by('-is_active', 'name')

    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(name__icontains=query)

    discount_type = request.GET.get('type', '').strip()
    if discount_type:
        queryset = queryset.filter(discount_type=discount_type)

    scope = request.GET.get('scope', '').strip()
    if scope:
        queryset = queryset.filter(scope=scope)

    status = request.GET.get('status', 'active').strip()
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'catalog/discount_list.html', {
        'page_obj': page_obj,
        'query': query,
        'discount_type': discount_type,
        'scope': scope,
        'status': status,
        'type_choices': Discount.DISCOUNT_TYPE_CHOICES,
        'scope_choices': Discount.SCOPE_CHOICES,
    })


@staff_or_admin
def discount_detail(request, pk):
    discount = get_object_or_404(Discount.objects.prefetch_related('products'), pk=pk)
    return render(request, 'catalog/discount_detail.html', {'discount': discount})


@admin_only
def discount_create(request):
    if request.method == 'POST':
        form = DiscountForm(request.POST)
        if form.is_valid():
            discount = form.save()
            messages.success(request, f"Discount '{discount.name}' created successfully.")
            return redirect('catalog:discount_detail', pk=discount.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = DiscountForm()
    return render(request, 'catalog/discount_form.html', {'form': form, 'title': 'Create Discount'})


@admin_only
def discount_update(request, pk):
    discount = get_object_or_404(Discount, pk=pk)
    if request.method == 'POST':
        form = DiscountForm(request.POST, instance=discount)
        if form.is_valid():
            discount = form.save()
            messages.success(request, f"Discount '{discount.name}' updated successfully.")
            return redirect('catalog:discount_detail', pk=discount.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = DiscountForm(instance=discount)
    return render(request, 'catalog/discount_form.html', {
        'form': form,
        'discount': discount,
        'title': f"Edit Discount: {discount.name}",
    })


@admin_only
def discount_delete(request, pk):
    discount = get_object_or_404(Discount, pk=pk)
    if request.method == 'POST':
        discount.is_active = False
        discount.save()
        messages.success(request, f"Discount '{discount.name}' deactivated.")
        return redirect('catalog:discount_list')
    return render(request, 'catalog/confirm_delete.html', {
        'object': discount,
        'title': f"Deactivate Discount: {discount.name}",
        'cancel_url': reverse('catalog:discount_detail', args=[discount.pk]),
    })


# -----------------------------------------------------------------------------
# Quotation Templates
# -----------------------------------------------------------------------------

@staff_or_admin
def quotation_template_list(request):
    queryset = QuotationTemplate.objects.select_related('plan').prefetch_related('lines').order_by('name')

    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(name__icontains=query)

    status = request.GET.get('status', 'active').strip()
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'catalog/template_list.html', {
        'page_obj': page_obj,
        'query': query,
        'status': status,
    })


@admin_only
def quotation_template_create(request):
    if request.method == 'POST':
        form = QuotationTemplateForm(request.POST)
        if form.is_valid():
            template = form.save()
            messages.success(request, f"Quotation template '{template.name}' created.")
            return redirect('catalog:template_detail', pk=template.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = QuotationTemplateForm()
    return render(request, 'catalog/template_form.html', {'form': form, 'title': 'Create Quotation Template'})


@staff_or_admin
def quotation_template_detail(request, pk):
    template = get_object_or_404(
        QuotationTemplate.objects.select_related('plan').prefetch_related('lines__product', 'lines__variant'),
        pk=pk
    )
    line_form = QuotationTemplateLineForm()
    return render(request, 'catalog/template_detail.html', {
        'template': template,
        'line_form': line_form,
    })


@admin_only
def quotation_template_update(request, pk):
    template = get_object_or_404(QuotationTemplate, pk=pk)
    if request.method == 'POST':
        form = QuotationTemplateForm(request.POST, instance=template)
        if form.is_valid():
            template = form.save()
            messages.success(request, f"Quotation template '{template.name}' updated.")
            return redirect('catalog:template_detail', pk=template.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = QuotationTemplateForm(instance=template)
    return render(request, 'catalog/template_form.html', {
        'form': form,
        'template': template,
        'title': f"Edit Quotation Template: {template.name}",
    })


@admin_only
def quotation_template_delete(request, pk):
    template = get_object_or_404(QuotationTemplate, pk=pk)
    if request.method == 'POST':
        template.is_active = False
        template.save()
        messages.success(request, f"Quotation template '{template.name}' deactivated.")
        return redirect('catalog:template_list')
    return render(request, 'catalog/confirm_delete.html', {
        'object': template,
        'title': f"Deactivate Quotation Template: {template.name}",
        'cancel_url': reverse('catalog:template_detail', args=[template.pk]),
    })


@admin_only
def quotation_template_line_add(request, pk):
    template = get_object_or_404(QuotationTemplate, pk=pk)
    if request.method == 'POST':
        form = QuotationTemplateLineForm(request.POST)
        if form.is_valid():
            line = form.save(commit=False)
            line.template = template
            line.save()
            messages.success(request, f"Added line: {line.product.name} (x{line.quantity}).")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field.title()}: {err}")
    return redirect('catalog:template_detail', pk=pk)


@admin_only
def quotation_template_line_delete(request, pk, line_pk):
    template = get_object_or_404(QuotationTemplate, pk=pk)
    line = get_object_or_404(QuotationTemplateLine, pk=line_pk, template=template)
    if request.method == 'POST':
        name = f"{line.product.name} x {line.quantity}"
        line.delete()
        messages.success(request, f"Line '{name}' removed from template.")
    return redirect('catalog:template_detail', pk=pk)
