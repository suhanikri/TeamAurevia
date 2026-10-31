from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import Plan, Product, ProductVariant, Tax, Discount
from subscriptions.models import Subscription, SubscriptionLine
from .engine import preview_billing, run_billing
from .models import Invoice, BillingRun, BillingFlag

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['*'])
class BillingEngineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin@subsentry.test', 'AdminPass123!')
        self.customer = User.objects.create_user('client@subsentry.test', 'ClientPass123!', role=User.ROLE_CUSTOMER)

        self.tax10 = Tax.objects.create(name='Tax 10%', rate=Decimal('10.00'))

        self.plan = Plan.objects.create(
            name='Monthly Cloud',
            price=Decimal('100.00'),
            billing_period=Plan.PERIOD_MONTHLY,
            auto_close=False,
            is_closable=True,
            is_pausable=True,
            is_renewable=True,
        )

        self.product = Product.objects.create(
            name='Cloud Server',
            sales_price=Decimal('100.00'),
            tax=self.tax10,
        )

        self.today = timezone.now().date()

    def test_preview_billing_does_not_modify_database(self):
        # Create an active subscription due today
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=self.today,
            next_invoice_date=self.today,
        )
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.product,
            quantity=1,
            unit_price=Decimal('100.00'),
            tax=self.tax10,
        )

        initial_invoices = Invoice.objects.count()
        initial_runs = BillingRun.objects.count()

        result = preview_billing(today=self.today)

        self.assertIsNone(result['run'])
        self.assertEqual(len(result['ready']), 1)
        self.assertEqual(result['ready'][0], sub)
        self.assertEqual(len(result['flagged']), 0)
        self.assertEqual(len(result['skipped']), 0)

        # Verified no database changes
        self.assertEqual(Invoice.objects.count(), initial_invoices)
        self.assertEqual(BillingRun.objects.count(), initial_runs)

    def test_run_billing_creates_invoice_with_correct_totals_and_taxes(self):
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=self.today,
            next_invoice_date=self.today,
            payment_terms_days=15,
        )
        # 2 units of 100 = 200. Tax 10% = 20. Total = 220.
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.product,
            quantity=2,
            unit_price=Decimal('100.00'),
            tax=self.tax10,
        )

        result = run_billing(today=self.today, user=self.user)

        self.assertEqual(len(result['generated']), 1)
        invoice = result['generated'][0]

        self.assertEqual(invoice.subscription, sub)
        self.assertEqual(invoice.customer, self.customer)
        self.assertEqual(invoice.status, Invoice.STATUS_DRAFT)
        self.assertEqual(invoice.due_date, self.today + timedelta(days=15))
        self.assertEqual(invoice.subtotal, Decimal('200.00'))
        self.assertEqual(invoice.tax_total, Decimal('20.00'))
        self.assertEqual(invoice.total, Decimal('220.00'))

        # next_invoice_date advanced
        sub.refresh_from_db()
        self.assertGreater(sub.next_invoice_date, self.today)

    def test_run_billing_twice_creates_zero_duplicates(self):
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=self.today,
            next_invoice_date=self.today,
        )
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.product,
            quantity=1,
            unit_price=Decimal('100.00'),
            tax=self.tax10,
        )

        # Run 1
        res1 = run_billing(today=self.today, user=self.user)
        self.assertEqual(len(res1['generated']), 1)
        self.assertEqual(len(res1['skipped']), 0)
        self.assertEqual(Invoice.objects.count(), 1)

        # Run 2 on the same day: subscription was advanced so 0 new invoices
        res2 = run_billing(today=self.today, user=self.user)
        self.assertEqual(len(res2['generated']), 0)
        self.assertEqual(Invoice.objects.count(), 1)

        # Run 3: Even if next_invoice_date is artificially set back to today's date
        sub.next_invoice_date = self.today
        sub.save()

        res3 = run_billing(today=self.today, user=self.user)
        self.assertEqual(len(res3['generated']), 0)
        self.assertEqual(len(res3['skipped']), 1)
        # Zero duplicate invoices created!
        self.assertEqual(Invoice.objects.count(), 1)

    def test_discount_applied_and_used_count_incremented_atomically(self):
        discount = Discount.objects.create(
            name='SAVE10',
            discount_type=Discount.TYPE_PERCENT,
            value=Decimal('10.00'),
            usage_limit=5,
            used_count=0,
            is_active=True,
        )
        sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            discount=discount,
            status=Subscription.STATUS_ACTIVE,
            start_date=self.today,
            next_invoice_date=self.today,
        )
        # Subtotal: 100. Discount 10%: 10. Tax 10% on 100: 10. Total = 100 - 10 + 10 = 100.
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.product,
            quantity=1,
            unit_price=Decimal('100.00'),
            tax=self.tax10,
        )

        result = run_billing(today=self.today, user=self.user)
        self.assertEqual(len(result['generated']), 1)
        inv = result['generated'][0]

        self.assertEqual(inv.discount_total, Decimal('10.00'))
        self.assertEqual(inv.total, Decimal('100.00'))

        # Check negative line
        disc_line = inv.lines.filter(is_discount=True).first()
        self.assertIsNotNone(disc_line)
        self.assertEqual(disc_line.amount, Decimal('-10.00'))

        # used_count incremented
        discount.refresh_from_db()
        self.assertEqual(discount.used_count, 1)

    def test_flagged_reasons(self):
        # 1. Paused subscription -> flagged with not_active
        sub_paused = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_PAUSED,
            start_date=self.today,
            next_invoice_date=self.today,
        )
        SubscriptionLine.objects.create(
            subscription=sub_paused, product=self.product, quantity=1, unit_price=Decimal('50.00'), tax=self.tax10,
        )

        # 2. Plan expired -> flagged with plan_expired
        plan_expired = Plan.objects.create(
            name='Expired Plan',
            price=Decimal('10.00'),
            billing_period=Plan.PERIOD_MONTHLY,
            available_to=self.today - timedelta(days=1),
        )
        sub_expired_plan = Subscription.objects.create(
            customer=self.customer,
            plan=plan_expired,
            status=Subscription.STATUS_ACTIVE,
            start_date=self.today,
            next_invoice_date=self.today,
        )
        SubscriptionLine.objects.create(
            subscription=sub_expired_plan, product=self.product, quantity=1, unit_price=Decimal('50.00'), tax=self.tax10,
        )

        # 3. Exhausted discount -> flagged with discount_exhausted
        disc_exhausted = Discount.objects.create(
            name='MaxedOut',
            discount_type=Discount.TYPE_FIXED,
            value=Decimal('20.00'),
            usage_limit=1,
            used_count=1,  # limit reached!
            is_active=True,
        )
        sub_exhausted_disc = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            discount=disc_exhausted,
            status=Subscription.STATUS_ACTIVE,
            start_date=self.today,
            next_invoice_date=self.today,
        )
        SubscriptionLine.objects.create(
            subscription=sub_exhausted_disc, product=self.product, quantity=1, unit_price=Decimal('50.00'), tax=self.tax10,
        )

        # 4. No lines -> flagged with no_lines
        sub_no_lines = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=self.today,
            next_invoice_date=self.today,
        )

        # 5. Line with no tax -> flagged with no_tax
        sub_no_tax = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=self.today,
            next_invoice_date=self.today,
        )
        SubscriptionLine.objects.create(
            subscription=sub_no_tax, product=self.product, quantity=1, unit_price=Decimal('50.00'), tax=None,
        )

        result = run_billing(today=self.today, user=self.user)

        self.assertEqual(len(result['generated']), 0)
        self.assertEqual(len(result['flagged']), 5)

        reasons = {item['reason'] for item in result['flagged']}
        self.assertIn(BillingFlag.REASON_NOT_ACTIVE, reasons)
        self.assertIn(BillingFlag.REASON_PLAN_EXPIRED, reasons)
        self.assertIn(BillingFlag.REASON_DISCOUNT_EXHAUSTED, reasons)
        self.assertIn(BillingFlag.REASON_NO_LINES, reasons)
        self.assertIn(BillingFlag.REASON_NO_TAX, reasons)

        # Verify BillingRun and BillingFlag saved
        run = result['run']
        self.assertIsNotNone(run)
        self.assertEqual(run.flagged, 5)
        self.assertEqual(BillingFlag.objects.filter(run=run).count(), 5)

