import os
import sys
import random
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta, date

import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.hashers import make_password
from django.utils import timezone
from accounts.models import User
from catalog.models import Tax, Product, ProductVariant, Plan, Discount, QuotationTemplate, QuotationTemplateLine
from subscriptions.models import Subscription, SubscriptionLine
from billing.models import Invoice, InvoiceLine, Payment, BillingFlag, BillingRun


def run_seed(reset=False):
    print("=" * 70)
    print("Starting SubSentry Database Seeding...")
    print("=" * 70)

    random.seed(42)
    today = timezone.now().date()

    if reset:
        print("[1/5] Reset requested: Purging existing operational data...")
        Payment.objects.all().delete()
        InvoiceLine.objects.all().delete()
        Invoice.objects.all().delete()
        BillingFlag.objects.all().delete()
        BillingRun.objects.all().delete()
        SubscriptionLine.objects.all().delete()
        Subscription.objects.all().delete()
        QuotationTemplateLine.objects.all().delete()
        QuotationTemplate.objects.all().delete()
        Discount.objects.all().delete()
        ProductVariant.objects.all().delete()
        Product.objects.all().delete()
        Plan.objects.all().delete()
        Tax.objects.all().delete()
        User.objects.exclude(is_superuser=True).delete()
        print("      Purge complete.")
    else:
        print("[1/5] Verifying existing core dataset...")

    # 1. Accounts
    print("[2/5] Creating user accounts...")
    shared_password_hash = make_password('Password@12345')
    admin_password_hash = make_password('Admin@12345')
    staff_password_hash = make_password('Staff@12345')
    demo_password_hash = make_password('Demo@12345')

    admin_user, _ = User.objects.get_or_create(
        email='admin@subsentry.test',
        defaults={
            'role': User.ROLE_ADMIN,
            'is_staff': True,
            'is_superuser': True,
            'password': admin_password_hash,
            'first_name': 'Chief',
            'last_name': 'Administrator',
        }
    )
    if admin_user.password != admin_password_hash:
        admin_user.password = admin_password_hash
        admin_user.save()

    staff_user, _ = User.objects.get_or_create(
        email='staff@subsentry.test',
        defaults={
            'role': User.ROLE_STAFF,
            'is_staff': True,
            'is_superuser': False,
            'password': staff_password_hash,
            'first_name': 'Sarah',
            'last_name': 'BillingOps',
        }
    )

    demo_customer, _ = User.objects.get_or_create(
        email='demo@subsentry.test',
        defaults={
            'role': User.ROLE_CUSTOMER,
            'is_staff': False,
            'is_superuser': False,
            'password': demo_password_hash,
            'first_name': 'Acme',
            'last_name': 'Enterprises',
        }
    )

    existing_customer_emails = set(User.objects.filter(role=User.ROLE_CUSTOMER).values_list('email', flat=True))
    customers_to_create = []
    num_customers = 1200
    for i in range(1, num_customers + 1):
        email = f"customer_{i:04d}@example.com"
        if email not in existing_customer_emails:
            customers_to_create.append(
                User(
                    email=email,
                    role=User.ROLE_CUSTOMER,
                    password=shared_password_hash,
                    first_name=f"Customer{i}",
                    last_name="Client",
                )
            )

    if customers_to_create:
        User.objects.bulk_create(customers_to_create, batch_size=500)
        print(f"      Created {len(customers_to_create)} customer accounts.")
    else:
        print(f"      Customer accounts already present.")

    all_customers = list(User.objects.filter(role=User.ROLE_CUSTOMER))

    # 2. Catalog (Taxes, Products, Plans, Discounts, Templates)
    print("[3/5] Setting up catalog...")
    tax_18, _ = Tax.objects.get_or_create(name='GST 18%', defaults={'rate': Decimal('18.00'), 'is_active': True})
    tax_5, _ = Tax.objects.get_or_create(name='GST 5%', defaults={'rate': Decimal('5.00'), 'is_active': True})

    prod_erp, _ = Product.objects.get_or_create(
        name='Odoo ERP Suite',
        defaults={'product_type': 'software', 'sales_price': Decimal('1200.00'), 'tax': tax_18, 'is_active': True}
    )
    var_odoo, _ = ProductVariant.objects.get_or_create(
        product=prod_erp, attribute='Brand', value='Odoo',
        defaults={'extra_price': Decimal('560.00')}
    )

    prod_crm, _ = Product.objects.get_or_create(
        name='CRM Pro',
        defaults={'product_type': 'software', 'sales_price': Decimal('450.00'), 'tax': tax_18, 'is_active': True}
    )
    prod_helpdesk, _ = Product.objects.get_or_create(
        name='Helpdesk Add-on',
        defaults={'product_type': 'addon', 'sales_price': Decimal('150.00'), 'tax': tax_18, 'is_active': True}
    )
    prod_analytics, _ = Product.objects.get_or_create(
        name='Analytics Add-on',
        defaults={'product_type': 'addon', 'sales_price': Decimal('250.00'), 'tax': tax_5, 'is_active': True}
    )

    catalog_products = [prod_erp, prod_crm, prod_helpdesk, prod_analytics]

    # Plans
    plan_daily, _ = Plan.objects.get_or_create(
        name='Startup Daily',
        defaults={'price': Decimal('25.00'), 'billing_period': Plan.PERIOD_DAILY, 'is_active': True}
    )
    plan_weekly, _ = Plan.objects.get_or_create(
        name='Growth Weekly',
        defaults={'price': Decimal('150.00'), 'billing_period': Plan.PERIOD_WEEKLY, 'is_active': True}
    )
    plan_monthly, _ = Plan.objects.get_or_create(
        name='Business Monthly',
        defaults={'price': Decimal('500.00'), 'billing_period': Plan.PERIOD_MONTHLY, 'is_active': True}
    )
    plan_yearly, _ = Plan.objects.get_or_create(
        name='Enterprise Yearly',
        defaults={'price': Decimal('5000.00'), 'billing_period': Plan.PERIOD_YEARLY, 'is_active': True}
    )

    # Deliberately expired plan for demo
    plan_expired, _ = Plan.objects.get_or_create(
        name='Legacy Sunset Plan',
        defaults={
            'price': Decimal('300.00'),
            'billing_period': Plan.PERIOD_MONTHLY,
            'is_active': True,
            'available_to': today - timedelta(days=30),
        }
    )

    all_plans = [plan_daily, plan_weekly, plan_monthly, plan_yearly]

    # Discounts
    disc_spring, _ = Discount.objects.get_or_create(
        name='Spring Promo 15%',
        defaults={'discount_type': Discount.TYPE_PERCENT, 'value': Decimal('15.00'), 'is_active': True}
    )
    disc_flat, _ = Discount.objects.get_or_create(
        name='Welcome Flat ₹50',
        defaults={'discount_type': Discount.TYPE_FIXED, 'value': Decimal('50.00'), 'is_active': True}
    )
    disc_blackfriday, _ = Discount.objects.get_or_create(
        name='Black Friday 2025 (Expired)',
        defaults={
            'discount_type': Discount.TYPE_PERCENT,
            'value': Decimal('30.00'),
            'is_active': True,
            'end_date': today - timedelta(days=45),
        }
    )
    disc_exhausted, _ = Discount.objects.get_or_create(
        name='Exhausted Founder Deal',
        defaults={
            'discount_type': Discount.TYPE_FIXED,
            'value': Decimal('100.00'),
            'usage_limit': 5,
            'used_count': 5,
            'is_active': True,
        }
    )

    # Templates
    tmpl_erp, _ = QuotationTemplate.objects.get_or_create(
        name='Standard ERP Onboarding',
        defaults={'plan': plan_monthly, 'validity_days': 30, 'is_active': True}
    )
    if not tmpl_erp.lines.exists():
        QuotationTemplateLine.objects.create(template=tmpl_erp, product=prod_erp, variant=var_odoo, quantity=1)
        QuotationTemplateLine.objects.create(template=tmpl_erp, product=prod_crm, quantity=2)

    tmpl_enterprise, _ = QuotationTemplate.objects.get_or_create(
        name='Enterprise All-in-One',
        defaults={'plan': plan_yearly, 'validity_days': 45, 'is_active': True}
    )
    if not tmpl_enterprise.lines.exists():
        QuotationTemplateLine.objects.create(template=tmpl_enterprise, product=prod_erp, variant=var_odoo, quantity=1)
        QuotationTemplateLine.objects.create(template=tmpl_enterprise, product=prod_crm, quantity=5)
        QuotationTemplateLine.objects.create(template=tmpl_enterprise, product=prod_helpdesk, quantity=5)
        QuotationTemplateLine.objects.create(template=tmpl_enterprise, product=prod_analytics, quantity=2)

    # 3. Subscriptions & Lines
    print("[4/5] Generating ~5,000 subscriptions and lines...")
    existing_sub_count = Subscription.objects.count()
    target_subs = 5000

    planted_bad_records = []

    if existing_sub_count < target_subs:
        needed = target_subs - existing_sub_count
        subs_to_create = []

        statuses = [
            (Subscription.STATUS_ACTIVE, 0.88),
            (Subscription.STATUS_DRAFT, 0.04),
            (Subscription.STATUS_QUOTATION, 0.03),
            (Subscription.STATUS_CONFIRMED, 0.03),
            (Subscription.STATUS_CLOSED, 0.02),
        ]
        status_choices = []
        for st, weight in statuses:
            status_choices.extend([st] * int(weight * 100))

        start_idx = existing_sub_count + 1

        # We designate the first 11 to be planted BAD records
        # All planted bad records have next_invoice_date = today so billing engine inspects them immediately!
        bad_configs = [
            {'desc': 'Already invoiced current period (duplicate prevention)', 'status': Subscription.STATUS_ACTIVE, 'plan': plan_monthly, 'disc': None, 'no_lines': False, 'no_tax': False, 'already_invoiced': True},
            {'desc': 'Plan expired (Legacy Sunset Plan)', 'status': Subscription.STATUS_ACTIVE, 'plan': plan_expired, 'disc': None, 'no_lines': False, 'no_tax': False, 'already_invoiced': False},
            {'desc': 'Plan expired (Legacy Sunset Plan)', 'status': Subscription.STATUS_ACTIVE, 'plan': plan_expired, 'disc': None, 'no_lines': False, 'no_tax': False, 'already_invoiced': False},
            {'desc': 'Discount exhausted (Exhausted Founder Deal)', 'status': Subscription.STATUS_ACTIVE, 'plan': plan_monthly, 'disc': disc_exhausted, 'no_lines': False, 'no_tax': False, 'already_invoiced': False},
            {'desc': 'Discount exhausted (Exhausted Founder Deal)', 'status': Subscription.STATUS_ACTIVE, 'plan': plan_yearly, 'disc': disc_exhausted, 'no_lines': False, 'no_tax': False, 'already_invoiced': False},
            {'desc': 'Paused contract due for billing', 'status': Subscription.STATUS_PAUSED, 'plan': plan_monthly, 'disc': None, 'no_lines': False, 'no_tax': False, 'already_invoiced': False},
            {'desc': 'Paused contract due for billing', 'status': Subscription.STATUS_PAUSED, 'plan': plan_weekly, 'disc': None, 'no_lines': False, 'no_tax': False, 'already_invoiced': False},
            {'desc': 'No product lines configured', 'status': Subscription.STATUS_ACTIVE, 'plan': plan_monthly, 'disc': None, 'no_lines': True, 'no_tax': False, 'already_invoiced': False},
            {'desc': 'No product lines configured', 'status': Subscription.STATUS_ACTIVE, 'plan': plan_yearly, 'disc': None, 'no_lines': True, 'no_tax': False, 'already_invoiced': False},
            {'desc': 'Product line missing tax configuration', 'status': Subscription.STATUS_ACTIVE, 'plan': plan_monthly, 'disc': None, 'no_lines': False, 'no_tax': True, 'already_invoiced': False},
            {'desc': 'Product line missing tax configuration', 'status': Subscription.STATUS_ACTIVE, 'plan': plan_daily, 'disc': None, 'no_lines': False, 'no_tax': True, 'already_invoiced': False},
        ]

        sub_configs = []

        # Setup first 11 as bad records
        for i, cfg in enumerate(bad_configs):
            num_str = f"SUB-BAD-{i+1:02d}"
            customer = all_customers[i % len(all_customers)]
            subs_to_create.append(
                Subscription(
                    number=num_str,
                    customer=customer,
                    plan=cfg['plan'],
                    discount=cfg['disc'],
                    status=cfg['status'],
                    start_date=today - timedelta(days=60),
                    next_invoice_date=today,
                    created_by=staff_user,
                )
            )
            planted_bad_records.append({
                'number': num_str,
                'customer': customer.email,
                'plan': cfg['plan'].name,
                'issue': cfg['desc'],
            })
            sub_configs.append(cfg)

        # Remaining ~4,989 clean subscriptions
        remaining_count = needed - len(bad_configs)
        for i in range(remaining_count):
            sub_num = f"SUB-{(start_idx + len(bad_configs) + i):05d}"
            customer = all_customers[i % len(all_customers)]
            plan = all_plans[i % len(all_plans)]
            status = random.choice(status_choices)

            # Assign valid discount occasionally
            disc = None
            if i % 10 == 0:
                disc = disc_spring
            elif i % 25 == 0:
                disc = disc_flat

            # Next invoice date distribution:
            # First 200 are due today or earlier (ready for billing run)
            if i < 200 and status == Subscription.STATUS_ACTIVE:
                days_offset = random.randint(-5, 0)
            else:
                days_offset = random.randint(1, 90)

            next_inv_date = today + timedelta(days=days_offset)

            subs_to_create.append(
                Subscription(
                    number=sub_num,
                    customer=customer,
                    plan=plan,
                    discount=disc,
                    status=status,
                    start_date=today - timedelta(days=random.randint(60, 365)),
                    next_invoice_date=next_inv_date,
                    created_by=staff_user,
                )
            )
            sub_configs.append({
                'desc': 'Normal',
                'status': status,
                'plan': plan,
                'disc': disc,
                'no_lines': False,
                'no_tax': False,
                'already_invoiced': False,
            })

        created_subs = Subscription.objects.bulk_create(subs_to_create, batch_size=1000)
        print(f"      Created {len(created_subs)} subscriptions.")

        # Re-fetch created subscriptions with IDs to attach lines
        all_new_subs = list(Subscription.objects.order_by('-id')[:len(created_subs)][::-1])

        print("      Generating subscription line items...")
        lines_to_create = []
        for sub, cfg in zip(all_new_subs, sub_configs):
            if cfg['no_lines']:
                continue

            # Pick 1 to 3 products
            if cfg['no_tax']:
                # Planted bad tax line
                lines_to_create.append(
                    SubscriptionLine(
                        subscription=sub,
                        product=prod_erp,
                        quantity=1,
                        unit_price=prod_erp.sales_price,
                        tax=None,  # Intentionally missing tax
                    )
                )
            else:
                num_lines = random.choice([1, 2, 3])
                for line_idx in range(num_lines):
                    prod = catalog_products[line_idx % len(catalog_products)]
                    var = var_odoo if prod == prod_erp else None
                    unit_price = prod.sales_price + (var.extra_price if var else Decimal('0.00'))
                    qty = random.randint(1, 5)

                    lines_to_create.append(
                        SubscriptionLine(
                            subscription=sub,
                            product=prod,
                            variant=var,
                            quantity=qty,
                            unit_price=unit_price,
                            tax=prod.tax or tax_18,
                        )
                    )

        SubscriptionLine.objects.bulk_create(lines_to_create, batch_size=1500)
        print(f"      Created {len(lines_to_create)} subscription line items.")

        # 4. Realistic Invoices & Payments (Past history + Overdue)
        print("[5/5] Creating realistic invoices, payments, and overdue records...")
        invoices_to_create = []
        invoice_configs = []

        # For the first planted bad sub (already_invoiced current period):
        bad_sub_1 = all_new_subs[0]
        p_start = bad_sub_1.next_invoice_date
        p_end = p_start + timedelta(days=29)
        invoices_to_create.append(
            Invoice(
                number='INV-DUP-CURRENT',
                subscription=bad_sub_1,
                customer=bad_sub_1.customer,
                status=Invoice.STATUS_PAID,
                invoice_date=today - timedelta(days=1),
                due_date=today + timedelta(days=14),
                period_start=p_start,
                period_end=p_end,
                subtotal=Decimal('1760.00'),
                tax_total=Decimal('316.80'),
                total=Decimal('2076.80'),
                amount_paid=Decimal('2076.80'),
            )
        )
        invoice_configs.append({'paid': True, 'amount_paid': Decimal('2076.80')})

        # Past invoices across ~2,000 active subscriptions
        active_subs = [s for s in all_new_subs if s.status == Subscription.STATUS_ACTIVE and not s.number.startswith('SUB-BAD-')][:2000]

        # We will create about 40 overdue invoices
        overdue_count = 0
        target_overdue = 40

        for idx, sub in enumerate(active_subs):
            inv_num = f"INV-HIST-{idx+1:05d}"
            # 40 overdue invoices
            if overdue_count < target_overdue and idx % 35 == 0:
                is_overdue = True
                overdue_count += 1
                days_ago = random.randint(15, 60)
                inv_date = today - timedelta(days=days_ago + 15)
                due_date = today - timedelta(days=days_ago)  # Due date in past
                p_st = inv_date
                p_en = due_date
                total_val = Decimal(str(random.choice([150, 450, 600, 1200, 2500])))
                tax_val = (total_val * Decimal('0.18')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                grand_total = total_val + tax_val
                # Partial payment or zero payment so balance > 0
                paid_val = Decimal('0.00') if idx % 2 == 0 else (grand_total * Decimal('0.3')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                inv_status = Invoice.STATUS_CONFIRMED
            else:
                is_overdue = False
                days_ago = random.randint(30, 180)
                inv_date = today - timedelta(days=days_ago)
                due_date = inv_date + timedelta(days=15)
                p_st = inv_date - timedelta(days=30)
                p_en = inv_date - timedelta(days=1)
                total_val = Decimal(str(random.choice([250, 500, 1200, 3000])))
                tax_val = (total_val * Decimal('0.18')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                grand_total = total_val + tax_val
                paid_val = grand_total
                inv_status = Invoice.STATUS_PAID

            invoices_to_create.append(
                Invoice(
                    number=inv_num,
                    subscription=sub,
                    customer=sub.customer,
                    status=inv_status,
                    invoice_date=inv_date,
                    due_date=due_date,
                    period_start=p_st,
                    period_end=p_en,
                    subtotal=total_val,
                    tax_total=tax_val,
                    total=grand_total,
                    amount_paid=paid_val,
                )
            )
            invoice_configs.append({'paid': (paid_val == grand_total), 'amount_paid': paid_val, 'date': inv_date})

        created_invoices = Invoice.objects.bulk_create(invoices_to_create, batch_size=1000)
        print(f"      Created {len(created_invoices)} invoices (including {overdue_count} overdue).")

        # Create Payments for invoices with amount_paid > 0
        all_new_invs = list(Invoice.objects.order_by('-id')[:len(created_invoices)][::-1])
        payments_to_create = []
        payment_methods = [Payment.METHOD_CARD, Payment.METHOD_BANK_TRANSFER, Payment.METHOD_UPI]

        for inv, cfg in zip(all_new_invs, invoice_configs):
            if cfg['amount_paid'] > Decimal('0.00'):
                p_date = cfg.get('date', inv.invoice_date) + timedelta(days=random.randint(1, 5))
                if p_date > today:
                    p_date = today
                payments_to_create.append(
                    Payment(
                        invoice=inv,
                        method=random.choice(payment_methods),
                        amount=cfg['amount_paid'],
                        payment_date=p_date,
                        note='Automated settlement via seed script',
                        recorded_by=staff_user,
                    )
                )

        Payment.objects.bulk_create(payments_to_create, batch_size=1000)
        print(f"      Created {len(payments_to_create)} payment records.")

    print("\n" + "=" * 70)
    print("PLANTED INTEGRITY ANOMALIES (Review Queue Benchmark Control Set)")
    print("=" * 70)
    print(f"{'Subscription':<14} | {'Customer Email':<28} | {'Planted Failure / Guardrail':<35}")
    print("-" * 80)
    for rec in planted_bad_records:
        print(f"{rec['number']:<14} | {rec['customer']:<28} | {rec['issue']:<35}")
    print("=" * 70)
    print(f"Total Subscriptions : {Subscription.objects.count()}")
    print(f"Total Invoices      : {Invoice.objects.count()}")
    print(f"Total Payments      : {Payment.objects.count()}")
    print(f"Active MRR Base     : {Subscription.objects.filter(status=Subscription.STATUS_ACTIVE).count()} active contracts")
    print("=" * 70)
    print("Seeding completed successfully!\n")


if __name__ == '__main__':
    reset_mode = '--reset' in sys.argv
    run_seed(reset=reset_mode)

