from decimal import Decimal
from django import forms
from .models import Product, ProductVariant, Plan, Tax, Discount, QuotationTemplate, QuotationTemplateLine


class BootstrapFormMixin:
    """
    Applies standard Bootstrap 5 widget classes to all form fields.
    - Checkboxes get 'form-check-input'
    - Select dropdowns get 'form-select'
    - Other inputs get 'form-control'
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            widget = field.widget
            css_class = widget.attrs.get('class', '')
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                widget.attrs['class'] = f"{css_class} form-check-input".strip()
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs['class'] = f"{css_class} form-select".strip()
            else:
                widget.attrs['class'] = f"{css_class} form-control".strip()


class ProductForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'product_type', 'sales_price', 'cost_price', 'tax', 'notes', 'is_active']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional internal notes...'}),
            'sales_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'cost_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
        labels = {
            'sales_price': 'Sales Price ($)',
            'cost_price': 'Cost Price ($)',
            'tax': 'Applicable Tax',
        }

    def clean_sales_price(self):
        price = self.cleaned_data.get('sales_price')
        if price is not None and price < Decimal('0.00'):
            raise forms.ValidationError("Sales price cannot be negative.")
        return price

    def clean_cost_price(self):
        price = self.cleaned_data.get('cost_price')
        if price is not None and price < Decimal('0.00'):
            raise forms.ValidationError("Cost price cannot be negative.")
        return price


class ProductVariantForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ['attribute', 'value', 'extra_price']
        widgets = {
            'attribute': forms.TextInput(attrs={'placeholder': 'e.g. Brand, Tier, Region'}),
            'value': forms.TextInput(attrs={'placeholder': 'e.g. Odoo, Enterprise, US-East'}),
            'extra_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
        }
        labels = {
            'extra_price': 'Extra Price ($)',
        }

    def clean_extra_price(self):
        price = self.cleaned_data.get('extra_price')
        if price is not None and price < Decimal('0.00'):
            raise forms.ValidationError("Extra price cannot be negative.")
        return price


class PlanForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Plan
        fields = [
            'name', 'price', 'billing_period', 'min_quantity',
            'available_from', 'available_to',
            'auto_close', 'is_closable', 'is_pausable', 'is_renewable',
            'is_active',
        ]
        widgets = {
            'available_from': forms.DateInput(attrs={'type': 'date'}),
            'available_to': forms.DateInput(attrs={'type': 'date'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'min_quantity': forms.NumberInput(attrs={'min': '1'}),
        }
        help_texts = {
            'auto_close': 'Automatically close the subscription at end of billing cycle.',
            'is_closable': 'Allow customer or staff to close the subscription before expiry.',
            'is_pausable': 'Allow subscription to be temporarily paused.',
            'is_renewable': 'Allow subscription to be renewed upon reaching expiry.',
            'min_quantity': 'Minimum number of units required to subscribe to this plan.',
        }

    def clean(self):
        cleaned_data = super().clean()
        available_from = cleaned_data.get('available_from')
        available_to = cleaned_data.get('available_to')
        if available_from and available_to and available_to < available_from:
            self.add_error('available_to', "Available To date cannot be earlier than Available From date.")
        return cleaned_data


class TaxForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Tax
        fields = ['name', 'rate', 'is_active']
        widgets = {
            'rate': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100', 'placeholder': 'e.g. 18.00'}),
        }
        labels = {
            'rate': 'Rate (%)',
        }

    def clean_rate(self):
        rate = self.cleaned_data.get('rate')
        if rate is not None:
            if rate < Decimal('0.00'):
                raise forms.ValidationError("Tax rate cannot be negative.")
            if rate > Decimal('100.00'):
                raise forms.ValidationError("Tax rate cannot exceed 100%.")
        return rate


class DiscountForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Discount
        fields = [
            'name', 'discount_type', 'value', 'min_purchase', 'min_quantity',
            'start_date', 'end_date', 'usage_limit', 'scope', 'products', 'is_active'
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'value': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'min_purchase': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'min_quantity': forms.NumberInput(attrs={'min': '0'}),
            'usage_limit': forms.NumberInput(attrs={'min': '1', 'placeholder': 'Leave blank for unlimited'}),
            'products': forms.SelectMultiple(attrs={'size': 6}),
        }
        help_texts = {
            'usage_limit': 'Maximum number of times this discount can be applied. Leave blank for unlimited.',
            'scope': 'Choose whether this discount applies to the whole subscription or specific products only.',
            'products': 'Hold Ctrl / Cmd to select multiple products (applies only when Scope is Specific Products).',
        }

    def clean(self):
        cleaned_data = super().clean()
        discount_type = cleaned_data.get('discount_type')
        value = cleaned_data.get('value')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if value is not None and value <= Decimal('0.00'):
            self.add_error('value', "Discount value must be greater than 0.")

        if discount_type == Discount.TYPE_PERCENT:
            if value is not None and (value <= Decimal('0.00') or value > Decimal('100.00')):
                self.add_error('value', "Percentage discount must be between 0 and 100%.")

        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', "End date cannot be earlier than start date.")

        return cleaned_data


class QuotationTemplateForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = QuotationTemplate
        fields = ['name', 'plan', 'validity_days', 'notes', 'is_active']
        widgets = {
            'validity_days': forms.NumberInput(attrs={'min': '1'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Terms or instructions for this quotation template...'}),
        }


class QuotationTemplateLineForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = QuotationTemplateLine
        fields = ['product', 'variant', 'quantity']
        widgets = {
            'quantity': forms.NumberInput(attrs={'min': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active products in the picker
        self.fields['product'].queryset = Product.objects.filter(is_active=True)

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is None or qty < 1:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        variant = cleaned_data.get('variant')
        if variant and product and variant.product_id != product.id:
            self.add_error('variant', f"Selected variant '{variant}' does not belong to product '{product.name}'.")
        return cleaned_data
