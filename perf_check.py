import os
import sys
import time

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
settings.ALLOWED_HOSTS = ['*']

from django.test import Client
from accounts.models import User


def run_perf_check():
    print("=" * 70)
    print("SubSentry Enterprise Performance Benchmark (< 2.0s Target)")
    print("=" * 70)

    admin_email = 'admin@subsentry.test'
    try:
        admin_user = User.objects.get(email=admin_email)
    except User.DoesNotExist:
        print(f"Error: Admin user '{admin_email}' not found. Please run 'python seed.py' first.")
        sys.exit(1)

    client = Client()
    # Force login
    client.force_login(admin_user)

    endpoints = [
        ('/dashboard/', 'Executive Dashboard (Reports)'),
        ('/reports/summary/', 'Plan Revenue Summary'),
        ('/billing/preview/', 'Billing Run Pre-Flight Preview'),
        ('/billing/review/', 'Billing Review Queue'),
        ('/payments/', 'Settlement Ledger (Payments List)'),
        ('/payments/outstanding/', 'Receivables Aging (Paid vs Outstanding)'),
        ('/invoices/', 'Invoices Workbench'),
        ('/subscriptions/', 'Subscription Registry'),
        ('/catalog/products/', 'Product Catalog Management'),
    ]

    all_passed = True

    # ANSI Colors
    GREEN = '\033[92m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

    print(f"{'Endpoint':<25} | {'Status':<8} | {'Latency':<10} | {'SLO (<2s)':<10} | {'Description'}")
    print("-" * 80)

    for url, desc in endpoints:
        start_time = time.perf_counter()
        try:
            response = client.get(url, HTTP_HOST='testserver')
            latency = time.perf_counter() - start_time
            status = response.status_code

            is_fast = latency < 2.0
            if not is_fast:
                all_passed = False
                status_color = RED
                verdict = f"{RED}[FAIL]{RESET}"
            else:
                status_color = GREEN
                verdict = f"{GREEN}[PASS]{RESET}"

            print(f"{url:<25} | {status_color}{status:<8}{RESET} | {latency:6.3f}s   | {verdict:<17} | {desc}")
        except Exception as e:
            latency = time.perf_counter() - start_time
            print(f"{url:<25} | {RED}ERR     {RESET} | {latency:6.3f}s   | {RED}[EXC]{RESET}        | {desc} - {e}")
            all_passed = False

    print("=" * 70)
    if all_passed:
        print(f"{GREEN}{BOLD}[OK] All benchmarked endpoints respond well under the 2.0-second limit!{RESET}")
    else:
        print(f"{RED}{BOLD}[WARNING] One or more endpoints exceeded 2.0 seconds latency target.{RESET}")
    print("=" * 70)


if __name__ == '__main__':
    run_perf_check()
