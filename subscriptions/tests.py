from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Plan, Product, ProductVariant, Tax, QuotationTemplate, QuotationTemplateLine
from .models import Subscription, SubscriptionLine
from .services import create_subscription_from_template, close_expired_subscriptions

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['*'])
class SubscriptionModelAndServiceTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user('cust@subsentry.test', 'CustPass123!', role=User.ROLE_CUSTOMER)
        self.tax = Tax.objects.create(name='VAT 20%', rate=Decimal('20.00'))
        self.plan = Plan.objects.create(
            name='Standard Monthly',
            price=Decimal('100.00'),
            billing_period=Plan.PERIOD_MONTHLY,
            auto_close=True,
            is_closable=True,
            is_pausable=True,
            is_renewable=True,
        )
        self.product = Product.objects.create(
            name='Cloud SaaS',
            sales_price=Decimal('50.00'),
            tax=self.tax,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            attribute='Brand',
            value='Odoo',
            extra_price=Decimal('560.00'),
        )
        self.template = QuotationTemplate.objects.create(
            name='Enterprise Bundle',
            plan=self.plan,
            validity_days=14,
        )
        self.tmpl_line = QuotationTemplateLine.objects.create(
            template=self.template,
            product=self.product,
            variant=self.variant,
            quantity=2,
        )

    def test_create_from_template(self):
        today = timezone.now().date()
        sub = create_subscription_from_template(
            customer=self.customer,
            template=self.template,
            start_date=today,
            payment_terms_days=30,
        )

        self.assertIsNotNone(sub.number)
        self.assertTrue(sub.number.startswith('SUB-'))
        self.assertEqual(sub.status, Subscription.STATUS_DRAFT)
        self.assertEqual(sub.quotation_valid_until, today + timedelta(days=14))
        self.assertEqual(sub.next_invoice_date, today)
        self.assertEqual(sub.payment_terms_days, 30)

        # Line copied correctly
        self.assertEqual(sub.lines.count(), 1)
        line = sub.lines.first()
        self.assertEqual(line.product, self.product)
        self.assertEqual(line.variant, self.variant)
        self.assertEqual(line.quantity, 2)
        # Unit price = 50 + 560 = 610
        self.assertEqual(line.unit_price, Decimal('610.00'))
        self.assertEqual(line.amount, Decimal('1220.00'))
        # Tax = 20% of 1220 = 244
        self.assertEqual(line.tax_amount, Decimal('244.00'))
        self.assertEqual(sub.subtotal, Decimal('1220.00'))
        self.assertEqual(sub.tax_total, Decimal('244.00'))
        self.assertEqual(sub.total, Decimal('1464.00'))

    def test_close_expired_subscriptions(self):
        today = timezone.now().date()
        # Active sub with auto_close=True and past expiry_date
        sub_expired = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=today - timedelta(days=60),
            expiry_date=today - timedelta(days=1),
        )
        # Active sub not yet expired
        sub_active = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=today,
            expiry_date=today + timedelta(days=30),
        )

        closed_count = close_expired_subscriptions(today)
        self.assertEqual(closed_count, 1)

        sub_expired.refresh_from_db()
        sub_active.refresh_from_db()
        self.assertEqual(sub_expired.status, Subscription.STATUS_CLOSED)
        self.assertEqual(sub_active.status, Subscription.STATUS_ACTIVE)

    def test_close_expired_management_command(self):
        call_command('close_expired')


@override_settings(ALLOWED_HOSTS=['*'])
class SubscriptionViewsAndPermissionsTests(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.staff_user = User.objects.create_user('staff@subsentry.test', 'StaffPass123!', role=User.ROLE_STAFF)
        self.customer1 = User.objects.create_user('c1@subsentry.test', 'CustPass123!', role=User.ROLE_CUSTOMER)
        self.customer2 = User.objects.create_user('c2@subsentry.test', 'CustPass123!', role=User.ROLE_CUSTOMER)

        self.plan_flexible = Plan.objects.create(
            name='Flexible Plan',
            price=Decimal('50.00'),
            billing_period=Plan.PERIOD_MONTHLY,
            auto_close=False,
            is_closable=True,
            is_pausable=True,
            is_renewable=True,
        )
        self.plan_strict = Plan.objects.create(
            name='Locked Plan',
            price=Decimal('100.00'),
            billing_period=Plan.PERIOD_YEARLY,
            auto_close=True,
            is_closable=False,
            is_pausable=False,
            is_renewable=False,
        )

        self.sub_cust1 = Subscription.objects.create(
            customer=self.customer1,
            plan=self.plan_flexible,
            status=Subscription.STATUS_DRAFT,
            start_date=timezone.now().date(),
        )

    def test_customer_isolation_detail_page(self):
        # Customer 2 cannot access Customer 1's subscription (404)
        self.client.force_login(self.customer2)
        resp = self.client.get(reverse('subscriptions:detail', args=[self.sub_cust1.pk]))
        self.assertEqual(resp.status_code, 404)

        # Customer 1 can access their own
        self.client.force_login(self.customer1)
        resp_own = self.client.get(reverse('subscriptions:detail', args=[self.sub_cust1.pk]))
        self.assertEqual(resp_own.status_code, 200)

        # Staff can access any subscription
        self.client.force_login(self.staff_user)
        resp_staff = self.client.get(reverse('subscriptions:detail', args=[self.sub_cust1.pk]))
        self.assertEqual(resp_staff.status_code, 200)

    def test_status_transitions_flow(self):
        self.client.force_login(self.staff_user)
        sub = self.sub_cust1

        # Draft -> Quotation
        self.client.post(reverse('subscriptions:action', args=[sub.pk, 'quotation']))
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.STATUS_QUOTATION)

        # Quotation -> Confirmed
        self.client.post(reverse('subscriptions:action', args=[sub.pk, 'confirm']))
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.STATUS_CONFIRMED)

        # Confirmed -> Active
        sub.next_invoice_date = None
        sub.save()
        self.client.post(reverse('subscriptions:action', args=[sub.pk, 'activate']))
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.STATUS_ACTIVE)
        # Sets next_invoice_date on activation if empty
        self.assertEqual(sub.next_invoice_date, sub.start_date)

    def test_plan_flags_pausable_and_closable(self):
        self.client.force_login(self.staff_user)

        # 1. Flexible plan: can pause and close early
        sub_flex = Subscription.objects.create(
            customer=self.customer1,
            plan=self.plan_flexible,
            status=Subscription.STATUS_ACTIVE,
            start_date=timezone.now().date(),
        )
        self.client.post(reverse('subscriptions:action', args=[sub_flex.pk, 'pause']))
        sub_flex.refresh_from_db()
        self.assertEqual(sub_flex.status, Subscription.STATUS_PAUSED)

        self.client.post(reverse('subscriptions:action', args=[sub_flex.pk, 'resume']))
        sub_flex.refresh_from_db()
        self.assertEqual(sub_flex.status, Subscription.STATUS_ACTIVE)

        self.client.post(reverse('subscriptions:action', args=[sub_flex.pk, 'close']))
        sub_flex.refresh_from_db()
        self.assertEqual(sub_flex.status, Subscription.STATUS_CLOSED)

        # 2. Strict plan: pause and early close are blocked
        sub_locked = Subscription.objects.create(
            customer=self.customer1,
            plan=self.plan_strict,
            status=Subscription.STATUS_ACTIVE,
            start_date=timezone.now().date(),
        )
        self.client.post(reverse('subscriptions:action', args=[sub_locked.pk, 'pause']))
        sub_locked.refresh_from_db()
        self.assertEqual(sub_locked.status, Subscription.STATUS_ACTIVE)  # Did not pause!

        self.client.post(reverse('subscriptions:action', args=[sub_locked.pk, 'close']))
        sub_locked.refresh_from_db()
        self.assertEqual(sub_locked.status, Subscription.STATUS_ACTIVE)  # Did not close!

    def test_renew_action(self):
        self.client.force_login(self.staff_user)
        today = timezone.now().date()
        sub_renew = Subscription.objects.create(
            customer=self.customer1,
            plan=self.plan_flexible,
            status=Subscription.STATUS_ACTIVE,
            start_date=today,
            expiry_date=today + timedelta(days=30),
        )
        old_expiry = sub_renew.expiry_date

        self.client.post(reverse('subscriptions:action', args=[sub_renew.pk, 'renew']))
        sub_renew.refresh_from_db()
        self.assertGreater(sub_renew.expiry_date, old_expiry)
