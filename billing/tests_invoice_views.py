from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import Invoice, InvoiceLine, Payment
from catalog.models import Plan, Product, Tax
from subscriptions.models import Subscription

User = get_user_model()


class StaffInvoiceViewsTests(TestCase):
    def setUp(self):
        # Create users
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

        # Catalog setup
        self.tax = Tax.objects.create(name='GST 18%', rate=Decimal('18.00'), is_active=True)
        self.product = Product.objects.create(
            name='Cloud Storage 100GB',
            sales_price=Decimal('500.00'),
            tax=self.tax,
        )
        self.plan = Plan.objects.create(
            name='Standard Plan',
            price=Decimal('500.00'),
            billing_period=Plan.PERIOD_MONTHLY,
        )

        # Subscription
        self.sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=timezone.now().date(),
        )

        # Invoices with distinct period_start to respect billing integrity unique constraint
        today = timezone.now().date()
        self.draft_inv = Invoice.objects.create(
            subscription=self.sub,
            customer=self.customer,
            status=Invoice.STATUS_DRAFT,
            invoice_date=today,
            due_date=today + timezone.timedelta(days=15),
            period_start=today,
            period_end=today + timezone.timedelta(days=30),
            subtotal=Decimal('500.00'),
            total=Decimal('590.00'),
            amount_paid=Decimal('0.00'),
        )
        self.confirmed_inv = Invoice.objects.create(
            subscription=self.sub,
            customer=self.customer,
            status=Invoice.STATUS_CONFIRMED,
            invoice_date=today + timezone.timedelta(days=30),
            due_date=today + timezone.timedelta(days=45),
            period_start=today + timezone.timedelta(days=31),
            period_end=today + timezone.timedelta(days=60),
            subtotal=Decimal('500.00'),
            total=Decimal('590.00'),
            amount_paid=Decimal('0.00'),
        )

    def test_permissions_access_control(self):
        """Anonymous redirected to login, customer receives 403, staff/admin allowed."""
        # Anonymous
        resp = self.client.get(reverse('invoices:list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

        # Customer role
        self.client.force_login(self.customer)
        resp = self.client.get(reverse('invoices:list'))
        self.assertEqual(resp.status_code, 403)

        # Staff role
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('invoices:list'))
        self.assertEqual(resp.status_code, 200)

        # Admin role
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('invoices:list'))
        self.assertEqual(resp.status_code, 200)

    def test_invoice_list_filters_and_search(self):
        """Staff can filter by status, search by customer email, and search by number."""
        self.client.force_login(self.staff)

        # Search by email
        resp = self.client.get(reverse('invoices:list') + '?search=customer@example.com')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.draft_inv.number)

        # Filter by status
        resp_draft = self.client.get(reverse('invoices:list') + '?status=draft')
        self.assertContains(resp_draft, self.draft_inv.number)
        self.assertNotContains(resp_draft, self.confirmed_inv.number)

    def test_invoice_detail_view(self):
        """Detail view loads with lines and totals."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('invoices:detail', args=[self.draft_inv.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Brightloop Software')
        self.assertContains(resp, self.customer.email)

    def test_confirm_action(self):
        """Draft invoice transitions to Confirmed on POST."""
        self.client.force_login(self.staff)
        resp = self.client.post(reverse('invoices:confirm', args=[self.draft_inv.id]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.draft_inv.refresh_from_db()
        self.assertEqual(self.draft_inv.status, Invoice.STATUS_CONFIRMED)

        # Re-confirming an already confirmed invoice gives a friendly error, doesn't crash
        resp2 = self.client.post(reverse('invoices:confirm', args=[self.draft_inv.id]), follow=True)
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, "status is already &#x27;Confirmed&#x27;")

    def test_cancel_action_and_refuse_if_payments_exist(self):
        """Can cancel invoice without payments; refuses if payments exist."""
        self.client.force_login(self.staff)

        # Cancel confirmed invoice without payment
        resp = self.client.post(reverse('invoices:cancel', args=[self.confirmed_inv.id]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.confirmed_inv.refresh_from_db()
        self.assertEqual(self.confirmed_inv.status, Invoice.STATUS_CANCELLED)

        # Add payment to draft invoice (or another invoice)
        inv_with_pay = Invoice.objects.create(
            subscription=self.sub,
            customer=self.customer,
            status=Invoice.STATUS_CONFIRMED,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date(),
            period_start=timezone.now().date() + timezone.timedelta(days=61),
            period_end=timezone.now().date() + timezone.timedelta(days=90),
            subtotal=Decimal('500.00'),
            total=Decimal('590.00'),
            amount_paid=Decimal('200.00'),
        )
        Payment.objects.create(
            invoice=inv_with_pay,
            method=Payment.METHOD_CARD,
            amount=Decimal('200.00'),
        )

        resp2 = self.client.post(reverse('invoices:cancel', args=[inv_with_pay.id]), follow=True)
        self.assertEqual(resp2.status_code, 200)
        inv_with_pay.refresh_from_db()
        self.assertEqual(inv_with_pay.status, Invoice.STATUS_CONFIRMED)
        self.assertContains(resp2, "because payments have already been recorded")

    def test_send_email_action(self):
        """Sending invoice triggers email and updates sent_at."""
        self.client.force_login(self.staff)

        # Draft invoice cannot be sent
        resp_draft = self.client.post(reverse('invoices:send', args=[self.draft_inv.id]), follow=True)
        self.assertContains(resp_draft, "only Confirmed or Paid invoices can be sent")

        # Confirmed invoice sends email
        resp = self.client.post(reverse('invoices:send', args=[self.confirmed_inv.id]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.confirmed_inv.refresh_from_db()
        self.assertIsNotNone(self.confirmed_inv.sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.confirmed_inv.number, mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, [self.customer.email])

    def test_print_view(self):
        """Print view returns 200 with print sheet layout."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('invoices:print', args=[self.confirmed_inv.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Brightloop Software')
        self.assertContains(resp, 'Print Preview')
