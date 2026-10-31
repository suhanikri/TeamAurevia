from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.utils import timezone

from catalog.models import Plan, QuotationTemplate, Product, ProductVariant, Tax, Discount
from .models import Subscription, SubscriptionLine

User = get_user_model()


class CreateFromTemplateForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=User.objects.all().order_by('email'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Customer",
    )
    template = forms.ModelChoiceField(
        queryset=QuotationTemplate.objects.filter(is_active=True).select_related('plan'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Quotation Template",
    )
    start_date = forms.DateField(
        initial=timezone.now,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="Start Date",
    )
    payment_terms_days = forms.IntegerField(
        initial=15,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label="Payment Terms (Days)",
    )


class ManualSubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = [
            'customer',
            'plan',
            'discount',
            'start_date',
            'expiry_date',
            'payment_terms_days',
        ]
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'plan': forms.Select(attrs={'class': 'form-select'}),
            'discount': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'payment_terms_days': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['discount'].required = False
        self.fields['expiry_date'].required = False


class SubscriptionLineForm(forms.ModelForm):
    class Meta:
        model = SubscriptionLine
        fields = ['product', 'variant', 'quantity', 'unit_price', 'tax']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'variant': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['variant'].required = False
        self.fields['tax'].required = False


SubscriptionLineFormSet = inlineformset_factory(
    Subscription,
    SubscriptionLine,
    form=SubscriptionLineForm,
    extra=1,
    can_delete=True,
)

