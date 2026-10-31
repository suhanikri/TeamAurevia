from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import Invoice, InvoiceLine, Payment
from catalog.models import Plan, Product, Tax
from subscriptions.models import Subscription, SubscriptionLine

User = get_user_model()


class CustomerPortalTests(TestCase):
    def setUp(self):
        # Create Customer A and Customer B
        self.customer_a = User.objects.create_user(
            email='customer_a@example.com',
            password='Password123!',
            role='customer',
        )
        self.customer_b = User.objects.create_user(
            email='customer_b@example.com',
            password='Password123!',
            role='customer',
        )
        self.staff_user = User.objects.create_user(
            email='staff@brightloop.com',
            password='Password123!',
            role='staff',
        )
        self.admin_user = User.objects.create_superuser(
            email='admin@brightloop.com',
            password='Password123!',
        )

        # Catalog setup
        self.tax = Tax.objects.create(name='GST 18%', rate=Decimal('18.00'), is_active=True)
        self.product = Product.objects.create(
            name='Cloud SaaS Pro',
            sales_price=Decimal('1000.00'),
            tax=self.tax,
        )
        self.plan = Plan.objects.create(
            name='Pro Monthly',
            price=Decimal('1000.00'),
            billing_period=Plan.PERIOD_MONTHLY,
        )

        # Customer A's subscription and invoice
        self.sub_a = Subscription.objects.create(
            customer=self.customer_a,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=timezone.now().date(),
        )
        self.line_a = SubscriptionLine.objects.create(
            subscription=self.sub_a,
            product=self.product,
            quantity=1,
            unit_price=Decimal('1000.00'),
            tax=self.tax,
        )
        self.inv_a = Invoice.objects.create(
            subscription=self.sub_a,
            customer=self.customer_a,
            status=Invoice.STATUS_CONFIRMED,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date(),
            period_start=timezone.now().date(),
            period_end=timezone.now().date(),
            subtotal=Decimal('1000.00'),
            total=Decimal('1180.00'),
            amount_paid=Decimal('0.00'),
        )
        self.inv_line_a = InvoiceLine.objects.create(
            invoice=self.inv_a,
            description='Cloud SaaS Pro subscription line',
            product=self.product,
            quantity=1,
            unit_price=Decimal('1000.00'),
            tax_rate=Decimal('18.00'),
            tax_amount=Decimal('180.00'),
            amount=Decimal('1000.00'),
        )
        self.pay_a = Payment.objects.create(
            invoice=self.inv_a,
            method=Payment.METHOD_UPI,
            amount=Decimal('500.00'),
            payment_date=timezone.now().date(),
            note='Initial partial payment via UPI',
        )

        # Customer B's subscription and invoice
        self.sub_b = Subscription.objects.create(
            customer=self.customer_b,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=timezone.now().date(),
        )
        self.inv_b = Invoice.objects.create(
            subscription=self.sub_b,
            customer=self.customer_b,
            status=Invoice.STATUS_CONFIRMED,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date(),
            period_start=timezone.now().date(),
            period_end=timezone.now().date(),
            subtotal=Decimal('1000.00'),
            total=Decimal('1180.00'),
            amount_paid=Decimal('0.00'),
        )

    def test_anonymous_redirected_to_login(self):
        """Anonymous users attempting to visit portal URLs must be redirected to login."""
        urls = [
            reverse('portal:subscription_list'),
            reverse('portal:subscription_detail', args=[self.sub_a.id]),
            reverse('portal:invoice_list'),
            reverse('portal:invoice_detail', args=[self.inv_a.id]),
            reverse('portal:payment_list'),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/accounts/login/', response.url)

    def test_admin_and_staff_redirected_to_dashboard(self):
        """Admins and staff visiting customer portal should be redirected to /dashboard/."""
        self.client.force_login(self.admin_user)
        resp_admin = self.client.get(reverse('portal:subscription_list'))
        self.assertEqual(resp_admin.status_code, 302)
        self.assertEqual(resp_admin.url, '/dashboard/')

        self.client.force_login(self.staff_user)
        resp_staff = self.client.get(reverse('portal:subscription_list'))
        self.assertEqual(resp_staff.status_code, 302)
        self.assertEqual(resp_staff.url, '/dashboard/')

    def test_customer_can_view_own_data(self):
        """Customer A can access their own subscriptions, invoices, and payments."""
        self.client.force_login(self.customer_a)

        # Subscriptions list
        resp = self.client.get(reverse('portal:subscription_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.sub_a.number)
        self.assertNotContains(resp, self.sub_b.number)

        # Subscription detail
        resp_sub = self.client.get(reverse('portal:subscription_detail', args=[self.sub_a.id]))
        self.assertEqual(resp_sub.status_code, 200)
        self.assertContains(resp_sub, 'Cloud SaaS Pro')
        self.assertContains(resp_sub, self.inv_a.number)

        # Invoices list
        resp_invs = self.client.get(reverse('portal:invoice_list'))
        self.assertEqual(resp_invs.status_code, 200)
        self.assertContains(resp_invs, self.inv_a.number)
        self.assertNotContains(resp_invs, self.inv_b.number)

        # Invoice detail
        resp_inv = self.client.get(reverse('portal:invoice_detail', args=[self.inv_a.id]))
        self.assertEqual(resp_inv.status_code, 200)
        self.assertContains(resp_inv, 'Brightloop Software')
        self.assertContains(resp_inv, 'Initial partial payment via UPI')

        # Payments list
        resp_pays = self.client.get(reverse('portal:payment_list'))
        self.assertEqual(resp_pays.status_code, 200)
        self.assertContains(resp_pays, self.inv_a.number)

    def test_customer_a_cannot_open_customer_b_subscription_returns_404(self):
        """Customer A cannot open Customer B's subscription, must return 404."""
        self.client.force_login(self.customer_a)
        response = self.client.get(reverse('portal:subscription_detail', args=[self.sub_b.id]))
        self.assertEqual(response.status_code, 404)

    def test_customer_a_cannot_open_customer_b_invoice_returns_404(self):
        """Customer A cannot open Customer B's invoice, must return 404."""
        self.client.force_login(self.customer_a)
        response = self.client.get(reverse('portal:invoice_detail', args=[self.inv_b.id]))
        self.assertEqual(response.status_code, 404)

    def test_invoice_status_filter(self):
        """Filtering by invoice status returns appropriate records."""
        self.client.force_login(self.customer_a)
        # Filter by confirmed
        resp = self.client.get(reverse('portal:invoice_list') + '?status=confirmed')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.inv_a.number)

        # Filter by draft (Customer A has no draft invoices)
        resp_draft = self.client.get(reverse('portal:invoice_list') + '?status=draft')
        self.assertEqual(resp_draft.status_code, 200)
        self.assertNotContains(resp_draft, self.inv_a.number)
