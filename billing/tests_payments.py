from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Plan
from subscriptions.models import Subscription
from .models import Invoice, Payment
from .payments import record_payment

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['*'])
class PaymentLogicTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user('staff@subsentry.test', 'StaffPass123!', role=User.ROLE_STAFF)
        self.customer = User.objects.create_user('cust@subsentry.test', 'CustPass123!', role=User.ROLE_CUSTOMER)
        self.plan = Plan.objects.create(name='Test Plan', price=Decimal('100.00'), billing_period='monthly')
        self.sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=timezone.now().date(),
        )
        self.invoice = Invoice.objects.create(
            subscription=self.sub,
            customer=self.customer,
            status=Invoice.STATUS_CONFIRMED,
            period_start=timezone.now().date(),
            period_end=timezone.now().date(),
            due_date=timezone.now().date(),
            total=Decimal('200.00'),
            amount_paid=Decimal('0.00'),
        )

    def test_partial_payment_keeps_invoice_confirmed(self):
        payment = record_payment(
            invoice=self.invoice,
            method='card',
            amount=Decimal('80.00'),
            user=self.staff_user,
        )

        self.invoice.refresh_from_db()
        self.assertEqual(payment.amount, Decimal('80.00'))
        self.assertEqual(self.invoice.amount_paid, Decimal('80.00'))
        self.assertEqual(self.invoice.balance, Decimal('120.00'))
        self.assertEqual(self.invoice.status, Invoice.STATUS_CONFIRMED)

    def test_full_payment_makes_invoice_paid(self):
        # Pay 80 first
        record_payment(invoice=self.invoice, method='card', amount=Decimal('80.00'), user=self.staff_user)
        self.invoice.refresh_from_db()

        # Pay remaining 120
        record_payment(invoice=self.invoice, method='upi', amount=Decimal('120.00'), user=self.staff_user)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('200.00'))
        self.assertEqual(self.invoice.balance, Decimal('0.00'))
        self.assertEqual(self.invoice.status, Invoice.STATUS_PAID)

    def test_overpayment_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            record_payment(invoice=self.invoice, method='bank_transfer', amount=Decimal('250.00'), user=self.staff_user)
        self.assertTrue('exceeds current invoice balance' in str(ctx.exception).lower())

    def test_zero_or_negative_amount_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            record_payment(invoice=self.invoice, method='cash', amount=Decimal('0.00'), user=self.staff_user)
        self.assertTrue('greater than zero' in str(ctx.exception).lower())

        with self.assertRaises(ValidationError) as ctx:
            record_payment(invoice=self.invoice, method='cash', amount=Decimal('-10.00'), user=self.staff_user)
        self.assertTrue('greater than zero' in str(ctx.exception).lower())

    def test_payment_on_draft_invoice_rejected(self):
        self.invoice.status = Invoice.STATUS_DRAFT
        self.invoice.save()

        with self.assertRaises(ValidationError) as ctx:
            record_payment(invoice=self.invoice, method='card', amount=Decimal('50.00'), user=self.staff_user)
        self.assertTrue('only be recorded on confirmed' in str(ctx.exception).lower())

    def test_payment_on_cancelled_invoice_rejected(self):
        self.invoice.status = Invoice.STATUS_CANCELLED
        self.invoice.save()

        with self.assertRaises(ValidationError) as ctx:
            record_payment(invoice=self.invoice, method='card', amount=Decimal('50.00'), user=self.staff_user)
        self.assertTrue('only be recorded on confirmed' in str(ctx.exception).lower())

    def test_payment_on_already_paid_invoice_rejected(self):
        self.invoice.status = Invoice.STATUS_PAID
        self.invoice.amount_paid = Decimal('200.00')
        self.invoice.save()

        with self.assertRaises(ValidationError) as ctx:
            record_payment(invoice=self.invoice, method='card', amount=Decimal('50.00'), user=self.staff_user)
        self.assertTrue('only be recorded on confirmed' in str(ctx.exception).lower())


@override_settings(ALLOWED_HOSTS=['*'])
class PaymentViewsTests(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.staff_user = User.objects.create_user('staff@subsentry.test', 'StaffPass123!', role=User.ROLE_STAFF)
        self.customer = User.objects.create_user('cust@subsentry.test', 'CustPass123!', role=User.ROLE_CUSTOMER)
        self.plan = Plan.objects.create(name='Pro Plan', price=Decimal('100.00'))
        self.sub = Subscription.objects.create(
            customer=self.customer,
            plan=self.plan,
            status=Subscription.STATUS_ACTIVE,
            start_date=timezone.now().date(),
        )
        self.invoice = Invoice.objects.create(
            subscription=self.sub,
            customer=self.customer,
            status=Invoice.STATUS_CONFIRMED,
            period_start=timezone.now().date(),
            period_end=timezone.now().date(),
            due_date=timezone.now().date(),
            total=Decimal('300.00'),
            amount_paid=Decimal('0.00'),
        )

    def test_record_payment_view_get_and_post(self):
        self.client.force_login(self.staff_user)
        url = reverse('payments:record', args=[self.invoice.pk])

        # GET
        res_get = self.client.get(url)
        self.assertEqual(res_get.status_code, 200)

        # POST valid payment
        res_post = self.client.post(url, {
            'method': 'card',
            'amount': '150.00',
            'payment_date': timezone.now().date().isoformat(),
            'note': 'Test Card Payment',
        })

        self.assertEqual(res_post.status_code, 302)
        self.assertEqual(res_post.headers['Location'], f"/invoices/{self.invoice.pk}/")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('150.00'))
        self.assertEqual(self.invoice.status, Invoice.STATUS_CONFIRMED)

    def test_payment_list_view(self):
        self.client.force_login(self.staff_user)
        Payment.objects.create(
            invoice=self.invoice,
            method='card',
            amount=Decimal('100.00'),
            payment_date=timezone.now().date(),
        )

        res = self.client.get(reverse('payments:list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '₹100.00')

    def test_outstanding_view(self):
        self.client.force_login(self.staff_user)
        res = self.client.get(reverse('payments:outstanding'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Paid vs Outstanding Invoices')
        self.assertContains(res, '₹300.00')
