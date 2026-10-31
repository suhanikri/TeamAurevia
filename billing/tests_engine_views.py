from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import BillingFlag, BillingRun, Invoice
from catalog.models import Plan, Product, Tax
from subscriptions.models import Subscription, SubscriptionLine

User = get_user_model()


class BillingEngineViewsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='admin@brightloop.com',
            password='AdminPassword123!',
        )
        self.staff = User.objects.create_user(
            email='staff@brightloop.com',
            password='StaffPassword123!',
            role='staff',
        )
        self.customer = User.objects.create_user(
            email='customer@example.com',
            password='CustomerPassword123!',
            role='customer',
        )

        self.tax = Tax.objects.create(name='GST 18%', rate=Decimal('18.00'), is_active=True)
        self.product = Product.objects.create(
            name='Cloud Pro Suite',
            sales_price=Decimal('2000.00'),
            tax=self.tax,
        )
        self.plan = Plan.objects.create(
            name='Enterprise Monthly',
            price=Decimal('2000.00'),
            billing_period=Plan.PERIOD_MONTHLY,
        )

        today = timezone.now().date()
        self.sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=today,
            next_invoice_date=today,
            payment_terms_days=15,
        )
        SubscriptionLine.objects.create(
            subscription=self.sub,
            product=self.product,
            quantity=1,
            unit_price=Decimal('2000.00'),
            tax=self.tax,
        )

    def test_permissions_access_control(self):
        """Anonymous redirected to login, customer receives 403, staff and admin allowed."""
        # Anonymous
        resp = self.client.get(reverse('billing_run:home'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

        # Customer role
        self.client.force_login(self.customer)
        resp = self.client.get(reverse('billing_run:home'))
        self.assertEqual(resp.status_code, 403)

        # Staff role
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('billing_run:home'))
        self.assertEqual(resp.status_code, 200)

        # Admin role
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('billing_run:home'))
        self.assertEqual(resp.status_code, 200)

    def test_billing_preview(self):
        """POST /billing/preview/ returns ready subscription."""
        self.client.force_login(self.staff)
        today_str = timezone.now().date().isoformat()
        resp = self.client.post(reverse('billing_run:preview'), {'target_date': today_str})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Billing Run Preview')
        self.assertContains(resp, self.sub.number)
        self.assertContains(resp, 'Run Billing Now')

    def test_billing_run_action_generates_invoice_and_shows_report(self):
        """POST /billing/run/ executes billing run, creates invoice, and displays report."""
        self.client.force_login(self.staff)
        today_str = timezone.now().date().isoformat()
        resp = self.client.post(reverse('billing_run:run'), {'target_date': today_str})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Billing Run Report')
        self.assertContains(resp, 'Newly Generated Invoices')

        # Check DB
        self.assertEqual(BillingRun.objects.count(), 1)
        run = BillingRun.objects.first()
        self.assertEqual(run.generated, 1)
        self.assertEqual(Invoice.objects.filter(subscription=self.sub).count(), 1)

    def test_review_queue_and_resolve_flag(self):
        """Staff can view review queue and resolve a flag."""
        self.client.force_login(self.staff)
        run = BillingRun.objects.create(total_due=Decimal('0.00'), run_by=self.staff)
        flag = BillingFlag.objects.create(
            run=run,
            subscription=self.sub,
            reason=BillingFlag.REASON_NOT_ACTIVE,
            message='Subscription is currently paused',
            resolved=False,
        )

        # View review queue
        resp = self.client.get(reverse('billing_run:review'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Subscription is currently paused')
        self.assertContains(resp, 'Mark Resolved')

        # Resolve flag
        resp_resolve = self.client.post(reverse('billing_run:resolve_flag', args=[flag.id]))
        self.assertRedirects(resp_resolve, reverse('billing_run:review'))
        flag.refresh_from_db()
        self.assertTrue(flag.resolved)
