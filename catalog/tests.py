from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client, override_settings
from django.urls import path, include, reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import Product, ProductVariant, Plan, Tax, Discount, QuotationTemplate, QuotationTemplateLine
from catalog.forms import PlanForm, DiscountForm, TaxForm
from catalog.pricing import get_line_price, calculate_line_tax, get_applicable_discounts
from subscriptions.models import Subscription, SubscriptionLine

# Test URL configuration allowing catalog urls to be tested directly
urlpatterns = [
    path('catalog/', include('catalog.urls', namespace='catalog')),
]


@override_settings(ROOT_URLCONF='catalog.tests')
class CatalogPhase1Tests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='AdminPassword123!',
        )
        self.staff_user = User.objects.create_user(
            email='staff@test.com',
            password='StaffPassword123!',
            role='staff'
        )
        self.customer_user = User.objects.create_user(
            email='customer@test.com',
            password='CustomerPassword123!',
            role='customer'
        )

        # Baseline Catalog Data
        self.tax_18 = Tax.objects.create(name='GST 18%', rate=Decimal('18.00'), is_active=True)
        self.product = Product.objects.create(
            name='BrightERP Core',
            product_type='software',
            sales_price=Decimal('1000.00'),
            cost_price=Decimal('400.00'),
            tax=self.tax_18,
            is_active=True
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            attribute='Brand',
            value='Odoo',
            extra_price=Decimal('560.00')
        )
        self.plan = Plan.objects.create(
            name='Professional Monthly',
            price=Decimal('99.00'),
            billing_period=Plan.PERIOD_MONTHLY,
            min_quantity=1,
            auto_close=False,
            is_closable=True,
            is_pausable=True,
            is_renewable=True,
            is_active=True
        )
        self.discount = Discount.objects.create(
            name='Launch Promo',
            discount_type=Discount.TYPE_PERCENT,
            value=Decimal('15.00'),
            min_purchase=Decimal('50.00'),
            min_quantity=1,
            scope=Discount.SCOPE_ALL,
            is_active=True
        )
        self.template = QuotationTemplate.objects.create(
            name='Standard ERP Bundle',
            plan=self.plan,
            validity_days=30,
            is_active=True
        )
        self.template_line = QuotationTemplateLine.objects.create(
            template=self.template,
            product=self.product,
            variant=self.variant,
            quantity=2
        )

    # -------------------------------------------------------------------------
    # Permissions Tests
    # -------------------------------------------------------------------------

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('catalog:product_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_customer_gets_403_on_catalog(self):
        self.client.force_login(self.customer_user)
        response = self.client.get(reverse('catalog:product_list'))
        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_but_cannot_create(self):
        self.client.force_login(self.staff_user)
        # Can view products list and detail
        res_list = self.client.get(reverse('catalog:product_list'))
        self.assertEqual(res_list.status_code, 200)

        res_detail = self.client.get(reverse('catalog:product_detail', args=[self.product.pk]))
        self.assertEqual(res_detail.status_code, 200)

        # Cannot access create view (gets 403)
        res_create = self.client.get(reverse('catalog:product_create'))
        self.assertEqual(res_create.status_code, 403)

    def test_admin_has_full_access(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('catalog:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catalog Management')
        self.assertContains(response, 'Products & Variants')

        res_products = self.client.get(reverse('catalog:product_list'))
        self.assertEqual(res_products.status_code, 200)
        self.assertContains(res_products, 'BrightERP Core')

    # -------------------------------------------------------------------------
    # Products & Variants Tests
    # -------------------------------------------------------------------------

    def test_product_create_and_variant_management(self):
        self.client.force_login(self.admin_user)
        # Create product
        res = self.client.post(reverse('catalog:product_create'), {
            'name': 'Cloud Hosting Tier',
            'product_type': 'service',
            'sales_price': '250.00',
            'cost_price': '100.00',
            'tax': self.tax_18.pk,
            'notes': 'Production grade',
            'is_active': True,
        })
        self.assertEqual(res.status_code, 302)
        product = Product.objects.get(name='Cloud Hosting Tier')
        self.assertEqual(product.sales_price, Decimal('250.00'))

        # Add variant (e.g. Attribute Brand, value Odoo, extra price 560)
        res_v = self.client.post(reverse('catalog:product_variant_add', args=[product.pk]), {
            'attribute': 'Region',
            'value': 'US-East',
            'extra_price': '45.00',
        })
        self.assertEqual(res_v.status_code, 302)
        self.assertTrue(product.variants.filter(attribute='Region', value='US-East').exists())

        # Delete variant
        variant = product.variants.get(attribute='Region', value='US-East')
        res_del_v = self.client.post(reverse('catalog:product_variant_delete', args=[product.pk, variant.pk]))
        self.assertEqual(res_del_v.status_code, 302)
        self.assertFalse(product.variants.filter(pk=variant.pk).exists())

    def test_product_soft_delete(self):
        self.client.force_login(self.admin_user)
        res = self.client.post(reverse('catalog:product_delete', args=[self.product.pk]), {
            'action': 'deactivate'
        })
        self.assertEqual(res.status_code, 302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    # -------------------------------------------------------------------------
    # Plans Tests & Validations
    # -------------------------------------------------------------------------

    def test_plan_form_date_validation(self):
        # available_to earlier than available_from
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        form = PlanForm(data={
            'name': 'Invalid Date Plan',
            'price': '50.00',
            'billing_period': 'monthly',
            'min_quantity': 1,
            'available_from': today,
            'available_to': yesterday,
            'auto_close': False,
            'is_closable': True,
            'is_pausable': True,
            'is_renewable': True,
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('available_to', form.errors)

    def test_plan_duplicate(self):
        self.client.force_login(self.admin_user)
        res = self.client.post(reverse('catalog:plan_duplicate', args=[self.plan.pk]))
        self.assertEqual(res.status_code, 302)
        duplicate = Plan.objects.get(name='Professional Monthly (Copy)')
        self.assertEqual(duplicate.price, self.plan.price)
        self.assertEqual(duplicate.billing_period, self.plan.billing_period)

    # -------------------------------------------------------------------------
    # Discount Validations Tests
    # -------------------------------------------------------------------------

    def test_discount_form_validation(self):
        # Percentage > 100 invalid
        form_high = DiscountForm(data={
            'name': 'Over 100%',
            'discount_type': Discount.TYPE_PERCENT,
            'value': '150.00',
            'min_purchase': '0.00',
            'min_quantity': 0,
            'scope': 'all',
            'is_active': True,
        })
        self.assertFalse(form_high.is_valid())
        self.assertIn('value', form_high.errors)

        # Value <= 0 invalid
        form_zero = DiscountForm(data={
            'name': 'Zero Discount',
            'discount_type': Discount.TYPE_FIXED,
            'value': '0.00',
            'min_purchase': '0.00',
            'min_quantity': 0,
            'scope': 'all',
            'is_active': True,
        })
        self.assertFalse(form_zero.is_valid())
        self.assertIn('value', form_zero.errors)

        # End date before start date invalid
        today = timezone.now().date()
        form_dates = DiscountForm(data={
            'name': 'Date Error',
            'discount_type': Discount.TYPE_PERCENT,
            'value': '10.00',
            'min_purchase': '0.00',
            'min_quantity': 0,
            'start_date': today,
            'end_date': today - timedelta(days=2),
            'scope': 'all',
            'is_active': True,
        })
        self.assertFalse(form_dates.is_valid())
        self.assertIn('end_date', form_dates.errors)

    # -------------------------------------------------------------------------
    # Quotation Templates Tests
    # -------------------------------------------------------------------------

    def test_quotation_template_lines(self):
        self.client.force_login(self.admin_user)
        # Add line
        res = self.client.post(reverse('catalog:template_line_add', args=[self.template.pk]), {
            'product': self.product.pk,
            'variant': self.variant.pk,
            'quantity': 3,
        })
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.template.lines.count(), 2)

        # Delete line
        res_del = self.client.post(
            reverse('catalog:template_line_delete', args=[self.template.pk, self.template_line.pk])
        )
        self.assertEqual(res_del.status_code, 302)
        self.assertFalse(QuotationTemplateLine.objects.filter(pk=self.template_line.pk).exists())


# =============================================================================
# Phase 2: Pricing Functions Tests
# =============================================================================

class PricingEngineTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email='sub_customer@test.com',
            password='CustomerPassword123!',
            role='customer'
        )
        self.plan = Plan.objects.create(
            name='Enterprise Annual',
            price=Decimal('1200.00'),
            billing_period=Plan.PERIOD_YEARLY,
            min_quantity=1,
            is_active=True
        )
        self.tax_18 = Tax.objects.create(name='GST 18%', rate=Decimal('18.00'), is_active=True)

        # Products
        self.software_prod = Product.objects.create(
            name='BrightERP Software',
            product_type='software',
            sales_price=Decimal('1000.00'),
            tax=self.tax_18,
            is_active=True
        )
        self.odoo_variant = ProductVariant.objects.create(
            product=self.software_prod,
            attribute='Brand',
            value='Odoo',
            extra_price=Decimal('560.00')
        )
        self.addon_prod = Product.objects.create(
            name='Priority Support',
            product_type='addon',
            sales_price=Decimal('200.00'),
            tax=self.tax_18,
            is_active=True
        )

    # 1. Variant price (+560)
    def test_get_line_price_with_and_without_variant(self):
        # Product 1000 + Odoo brand 560 = 1560.00
        price_with_variant = get_line_price(self.software_prod, self.odoo_variant)
        self.assertEqual(price_with_variant, Decimal('1560.00'))

        # Product 1000 without variant = 1000.00
        price_without_variant = get_line_price(self.software_prod, None)
        self.assertEqual(price_without_variant, Decimal('1000.00'))

    # 2. Line tax calculation & ROUND_HALF_UP rounding
    def test_calculate_line_tax(self):
        # 1000.00 * 18% = 180.00
        tax_amt = calculate_line_tax(Decimal('1000.00'), self.tax_18)
        self.assertEqual(tax_amt, Decimal('180.00'))

        # None tax returns 0.00
        self.assertEqual(calculate_line_tax(Decimal('1000.00'), None), Decimal('0.00'))

        # Test ROUND_HALF_UP rounding: 12.355 * 10% = 1.2355 -> 1.24
        tax_10 = Tax.objects.create(name='Tax 10%', rate=Decimal('10.00'), is_active=True)
        tax_rounded = calculate_line_tax(Decimal('12.355'), tax_10)
        self.assertEqual(tax_rounded, Decimal('1.24'))

    # 3. Percent and fixed whole-subscription discounts
    def test_percent_and_fixed_discounts(self):
        sub = Subscription.objects.create(customer=self.customer, plan=self.plan)
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.software_prod,
            quantity=1,
            unit_price=Decimal('1000.00')
        )
        self.assertEqual(sub.subtotal, Decimal('1000.00'))

        # Percent discount: 15% on 1000.00 = 150.00
        pct_discount = Discount.objects.create(
            name='15% Off',
            discount_type=Discount.TYPE_PERCENT,
            value=Decimal('15.00'),
            scope=Discount.SCOPE_ALL,
            is_active=True
        )
        sub.discount = pct_discount
        sub.save()

        discounts = get_applicable_discounts(sub)
        self.assertEqual(len(discounts), 1)
        self.assertEqual(discounts[0][0], pct_discount)
        self.assertEqual(discounts[0][1], Decimal('150.00'))

        # Fixed discount: $250.00 on 1000.00 = 250.00
        fixed_discount = Discount.objects.create(
            name='$250 Off',
            discount_type=Discount.TYPE_FIXED,
            value=Decimal('250.00'),
            scope=Discount.SCOPE_ALL,
            is_active=True
        )
        sub.discount = fixed_discount
        sub.save()

        discounts_fixed = get_applicable_discounts(sub)
        self.assertEqual(len(discounts_fixed), 1)
        self.assertEqual(discounts_fixed[0][0], fixed_discount)
        self.assertEqual(discounts_fixed[0][1], Decimal('250.00'))

        # Fixed discount capped at base amount (e.g. $1500 off $1000 = $1000)
        huge_discount = Discount.objects.create(
            name='Huge $1500 Off',
            discount_type=Discount.TYPE_FIXED,
            value=Decimal('1500.00'),
            scope=Discount.SCOPE_ALL,
            is_active=True
        )
        sub.discount = huge_discount
        sub.save()
        discounts_huge = get_applicable_discounts(sub)
        self.assertEqual(discounts_huge[0][1], Decimal('1000.00'))

    # 4. Expired discount not applied
    def test_expired_discount_not_applied(self):
        today = timezone.now().date()
        expired_discount = Discount.objects.create(
            name='Yesterday Promo',
            discount_type=Discount.TYPE_PERCENT,
            value=Decimal('20.00'),
            scope=Discount.SCOPE_ALL,
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=1),  # Expired yesterday
            is_active=True
        )
        sub = Subscription.objects.create(customer=self.customer, plan=self.plan, discount=expired_discount)
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.software_prod,
            quantity=1,
            unit_price=Decimal('1000.00')
        )

        discounts = get_applicable_discounts(sub, on=today)
        self.assertEqual(discounts, [])

    # 5. Exhausted usage limit not applied
    def test_exhausted_usage_limit_not_applied(self):
        exhausted_discount = Discount.objects.create(
            name='Limited 10 Uses',
            discount_type=Discount.TYPE_FIXED,
            value=Decimal('50.00'),
            scope=Discount.SCOPE_ALL,
            usage_limit=10,
            used_count=10,  # Exhausted
            is_active=True
        )
        sub = Subscription.objects.create(customer=self.customer, plan=self.plan, discount=exhausted_discount)
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.software_prod,
            quantity=1,
            unit_price=Decimal('1000.00')
        )

        discounts = get_applicable_discounts(sub)
        self.assertEqual(discounts, [])

    # 6. Min quantity not met
    def test_min_quantity_not_met(self):
        bulk_discount = Discount.objects.create(
            name='Bulk Purchase 5+ Units',
            discount_type=Discount.TYPE_PERCENT,
            value=Decimal('25.00'),
            min_quantity=5,
            scope=Discount.SCOPE_ALL,
            is_active=True
        )
        sub = Subscription.objects.create(customer=self.customer, plan=self.plan, discount=bulk_discount)
        line = SubscriptionLine.objects.create(
            subscription=sub,
            product=self.software_prod,
            quantity=3,  # Less than min_quantity 5
            unit_price=Decimal('1000.00')
        )

        # Fails min_quantity
        self.assertEqual(get_applicable_discounts(sub), [])

        # Passes when quantity >= 5
        line.quantity = 5
        line.save()
        discounts = get_applicable_discounts(sub)
        self.assertEqual(len(discounts), 1)
        self.assertEqual(discounts[0][1], Decimal('1250.00'))  # 25% of 5000.00

    # 7. Product-scope discount applying only to matching lines
    def test_product_scope_discount_only_matching_lines(self):
        # Product-scoped discount applies automatically to lines whose product is in discount.products
        addon_discount = Discount.objects.create(
            name='Support Addon 50% Off',
            discount_type=Discount.TYPE_PERCENT,
            value=Decimal('50.00'),
            scope=Discount.SCOPE_PRODUCTS,
            is_active=True
        )
        addon_discount.products.add(self.addon_prod)

        # Subscription with software ($1000) and addon ($200)
        sub = Subscription.objects.create(customer=self.customer, plan=self.plan)
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.software_prod,
            quantity=1,
            unit_price=Decimal('1000.00')
        )
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.addon_prod,
            quantity=2,
            unit_price=Decimal('200.00')  # 2 * 200 = 400.00
        )

        # Subtotal is 1000 + 400 = 1400.00
        self.assertEqual(sub.subtotal, Decimal('1400.00'))

        # Addon discount applies ONLY to addon line (400.00 * 50% = 200.00), NOT software
        discounts = get_applicable_discounts(sub)
        self.assertEqual(len(discounts), 1)
        self.assertEqual(discounts[0][0], addon_discount)
        self.assertEqual(discounts[0][1], Decimal('200.00'))

    # 8. Subscription with no lines or no discount never raises
    def test_empty_subscription_never_raises(self):
        empty_sub = Subscription.objects.create(customer=self.customer, plan=self.plan)
        self.assertEqual(get_applicable_discounts(empty_sub), [])
        self.assertEqual(get_applicable_discounts(None), [])
