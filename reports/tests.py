from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import Plan, Product, Tax
from subscriptions.models import Subscription, SubscriptionLine
from billing.models import Invoice, Payment, BillingFlag, BillingRun
from reports.services import calculate_mrr, get_dashboard_metrics, get_plan_summary_data


@override_settings(ALLOWED_HOSTS=['*'])
class ReportServicesAndViewsTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email='admin@reports.test', password='Password@123', role=User.ROLE_ADMIN)
        self.staff = User.objects.create_user(email='staff@reports.test', password='Password@123', role=User.ROLE_STAFF)
        self.customer = User.objects.create_user(email='customer@reports.test', password='Password@123', role=User.ROLE_CUSTOMER)

        self.tax_0 = Tax.objects.create(name='Zero Tax', rate=Decimal('0.00'))
        self.prod = Product.objects.create(name='Core SaaS', tax=self.tax_0)

        # Plans with different billing periods
        self.plan_yearly = Plan.objects.create(name='Enterprise Yearly', billing_period=Plan.PERIOD_YEARLY)
        self.plan_weekly = Plan.objects.create(name='Sprint Weekly', billing_period=Plan.PERIOD_WEEKLY)
        self.plan_daily = Plan.objects.create(name='Compute Daily', billing_period=Plan.PERIOD_DAILY)
        self.plan_monthly = Plan.objects.create(name='Pro Monthly', billing_period=Plan.PERIOD_MONTHLY)

    def test_mrr_calculations(self):
        """
        Verify MRR conversion logic:
        - Yearly 1200 = 100 per month
        - Weekly 100 = 433.33 per month (100 * 52 / 12 = 433.333...)
        - Daily 10 = 300 per month (10 * 30 = 300)
        - Monthly 50 = 50 per month
        """
        today = timezone.now().date()

        # 1. Yearly 1200 (Active)
        sub_yr = Subscription.objects.create(
            number='SUB-YR', customer=self.customer, plan=self.plan_yearly,
            status=Subscription.STATUS_ACTIVE, start_date=today, next_invoice_date=today
        )
        SubscriptionLine.objects.create(
            subscription=sub_yr, product=self.prod, quantity=1, unit_price=Decimal('1200.00'), tax=self.tax_0
        )

        # 2. Weekly 100 (Active)
        sub_wk = Subscription.objects.create(
            number='SUB-WK', customer=self.customer, plan=self.plan_weekly,
            status=Subscription.STATUS_ACTIVE, start_date=today, next_invoice_date=today
        )
        SubscriptionLine.objects.create(
            subscription=sub_wk, product=self.prod, quantity=1, unit_price=Decimal('100.00'), tax=self.tax_0
        )

        # 3. Daily 10 (Active)
        sub_dy = Subscription.objects.create(
            number='SUB-DY', customer=self.customer, plan=self.plan_daily,
            status=Subscription.STATUS_ACTIVE, start_date=today, next_invoice_date=today
        )
        SubscriptionLine.objects.create(
            subscription=sub_dy, product=self.prod, quantity=1, unit_price=Decimal('10.00'), tax=self.tax_0
        )

        # 4. Monthly 50 (Active)
        sub_mo = Subscription.objects.create(
            number='SUB-MO', customer=self.customer, plan=self.plan_monthly,
            status=Subscription.STATUS_ACTIVE, start_date=today, next_invoice_date=today
        )
        SubscriptionLine.objects.create(
            subscription=sub_mo, product=self.prod, quantity=1, unit_price=Decimal('50.00'), tax=self.tax_0
        )

        # Draft subscription should NOT be counted in MRR
        sub_draft = Subscription.objects.create(
            number='SUB-DRAFT', customer=self.customer, plan=self.plan_monthly,
            status=Subscription.STATUS_DRAFT, start_date=today, next_invoice_date=today
        )
        SubscriptionLine.objects.create(
            subscription=sub_draft, product=self.prod, quantity=1, unit_price=Decimal('999.00'), tax=self.tax_0
        )

        total_mrr, period_totals = calculate_mrr()

        self.assertEqual(period_totals[Plan.PERIOD_YEARLY], Decimal('100.00'))
        self.assertEqual(period_totals[Plan.PERIOD_WEEKLY], Decimal('433.33'))
        self.assertEqual(period_totals[Plan.PERIOD_DAILY], Decimal('300.00'))
        self.assertEqual(period_totals[Plan.PERIOD_MONTHLY], Decimal('50.00'))
        self.assertEqual(total_mrr, Decimal('883.33'))

    def test_overdue_and_risk_metrics(self):
        """
        Verify overdue logic and Revenue at Risk calculation:
        - Confirmed + past due + balance > 0 => Overdue
        - Revenue at Risk = overdue balance + flagged active sub line total
        """
        today = timezone.now().date()
        sub = Subscription.objects.create(
            number='SUB-RISK', customer=self.customer, plan=self.plan_monthly,
            status=Subscription.STATUS_ACTIVE, start_date=today, next_invoice_date=today
        )
        SubscriptionLine.objects.create(
            subscription=sub, product=self.prod, quantity=1, unit_price=Decimal('200.00'), tax=self.tax_0
        )

        # Invoice 1: Overdue Confirmed
        Invoice.objects.create(
            number='INV-OD', subscription=sub, customer=self.customer,
            status=Invoice.STATUS_CONFIRMED, invoice_date=today - timedelta(days=20),
            due_date=today - timedelta(days=5), period_start=today - timedelta(days=20),
            period_end=today - timedelta(days=5), subtotal=Decimal('100.00'),
            tax_total=Decimal('0.00'), total=Decimal('100.00'), amount_paid=Decimal('20.00')
        )  # balance = 80.00

        # Invoice 2: Past due but Paid (NOT overdue)
        Invoice.objects.create(
            number='INV-PAID', subscription=sub, customer=self.customer,
            status=Invoice.STATUS_PAID, invoice_date=today - timedelta(days=20),
            due_date=today - timedelta(days=5), period_start=today - timedelta(days=35),
            period_end=today - timedelta(days=21), subtotal=Decimal('50.00'),
            tax_total=Decimal('0.00'), total=Decimal('50.00'), amount_paid=Decimal('50.00')
        )

        # Invoice 3: Future due Confirmed (NOT overdue)
        Invoice.objects.create(
            number='INV-FUT', subscription=sub, customer=self.customer,
            status=Invoice.STATUS_CONFIRMED, invoice_date=today,
            due_date=today + timedelta(days=10), period_start=today,
            period_end=today + timedelta(days=30), subtotal=Decimal('70.00'),
            tax_total=Decimal('0.00'), total=Decimal('70.00'), amount_paid=Decimal('0.00')
        )

        # Plant unresolved billing flag on active sub
        run = BillingRun.objects.create(is_preview=False)
        BillingFlag.objects.create(
            run=run, subscription=sub, reason=BillingFlag.REASON_OTHER,
            message='Planted test error', resolved=False
        )

        metrics = get_dashboard_metrics(today=today)

        self.assertEqual(metrics['count_overdue'], 1)
        self.assertEqual(metrics['total_overdue'], Decimal('80.00'))
        self.assertEqual(metrics['total_outstanding'], Decimal('150.00'))  # 80 + 70
        # Revenue at risk = 80 (overdue) + 200 (sub lines) = 280.00
        self.assertEqual(metrics['revenue_at_risk'], Decimal('280.00'))
        self.assertEqual(metrics['unresolved_flags_count'], 1)

    def test_dashboard_and_summary_views_access(self):
        """
        Verify view permissions and status codes.
        """
        # Unauthenticated -> redirect to login
        res = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(res.status_code, 302)

        # Customer -> 403 Forbidden
        self.client.force_login(self.customer)
        res = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(res.status_code, 403)

        # Staff -> 200 OK
        self.client.force_login(self.staff)
        res = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Subscription Revenue Control Tower')

        # Summary view
        res = self.client.get(reverse('reports:summary'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Plan Revenue Summary')

        # Summary CSV export
        res_csv = self.client.get(reverse('reports:summary') + '?export=csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv['Content-Type'], 'text/csv')
        self.assertIn('Enterprise Yearly', res_csv.content.decode('utf-8'))
