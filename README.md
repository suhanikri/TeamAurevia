# SubSentry

> *"Every subscription billed once, billed right."*

SubSentry is a high-performance, audit-grade subscription management and recurring billing platform built for enterprise software businesses. Designed specifically to eliminate revenue leakage, prevent costly double-billing errors, and provide finance leaders with real-time operational control, SubSentry processes thousands of subscriptions in milliseconds while maintaining zero-tolerance transactional integrity.

---

## 🌟 The Problem & The Billing Integrity Engine

In recurring SaaS billing, edge cases cost millions:
- Duplicate invoices issued for the same cycle when billing runs retry or overlap.
- Subscriptions silently billing against expired pricing plans or exhausted discount vouchers.
- Invoices generated without compliant tax rules, creating accounting write-offs.
- Paused contracts improperly billed during suspension periods.

### How the Billing Integrity Engine Works
SubSentry features a deterministic **Billing Integrity Engine** that inspects candidate subscriptions prior to generating receivables:
1. **Double-Billing Barrier:** Enforces a database-level `UniqueConstraint` on `(subscription_id, period_start)` across all active invoices. It is architecturally impossible for a customer to be invoiced twice for the same billing window.
2. **Deterministic Pre-Flight Evaluation:** Every contract is verified against 6 guardrails:
   - Subscription lifecycle status must be strictly `Active`.
   - Contract Plan must be within its active validity dates (`available_from` to `available_to`).
   - Line items must exist and carry active tax rates.
   - Any attached discount vouchers must be valid, active, and within usage limits.
3. **Automated Review Queue:** Rather than failing silently or halting the entire billing batch, non-compliant subscriptions are flagged, categorized, and isolated into an interactive **Review Queue** (`/billing/review/`) with root-cause diagnostics, allowing billing operations to remediate records before re-queueing.

---

## 🛠️ Tech Stack

- **Backend:** Python 3.13, Django 6.1
- **Database:** SQLite (optimized with multi-column indices, DB-level aggregation, and bulk operations)
- **Frontend:** Django Server-Rendered Templates, Bootstrap 5 CDN, Bootstrap Icons
- **Interactive Visualizations:** Chart.js 4.4 CDN (zero external Node.js build dependencies)
- **Scripting:** Vanilla JavaScript (fast, reactive UI widgets and modal toggles)

---

## 🚀 Quickstart & Setup (Windows PowerShell)

Follow these steps to clone, configure, and launch SubSentry locally:

```powershell
# 1. Clone repository
git clone https://github.com/suhanikri/TeamAurevia.git
cd TeamAurevia

# 2. Create and activate virtual environment
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Apply database migrations
python manage.py migrate

# 5. Populate deterministic seed dataset (1,200 users, 5,000 subscriptions, 2,000 invoices)
python seed.py --reset

# 6. Verify sub-2-second performance benchmark
python perf_check.py

# 7. Start local development server
python manage.py runserver
```

Open your browser at: **`http://127.0.0.1:8000/`**

---

## 🔑 Demo Credentials

| Role | Email | Password | Access Level |
| :--- | :--- | :--- | :--- |
| **Admin (Superuser)** | `admin@subsentry.test` | `Admin@12345` | Complete system access, staff management, catalog configuration |
| **Staff (Billing Ops)** | `staff@subsentry.test` | `Staff@12345` | Subscriptions, billing runs, payment settlements, dashboard |
| **Customer (Portal)** | `demo@subsentry.test` | `Demo@12345` | Customer self-service portal, view own invoices and contracts |

*(Note: All other 1,200 seeded customers use password `Password@12345`)*

---

## 👥 Role Permissions Matrix

| Feature / URL Path | Admin | Staff | Customer | Anonymous |
| :--- | :---: | :---: | :---: | :---: |
| **Executive Dashboard** (`/dashboard/`) |  Yes |  Yes |  No (403) |  Redirect (302) |
| **Plan Revenue Summary** (`/reports/summary/`) |  Yes |  Yes |  No (403) |  Redirect (302) |
| **Billing Integrity Engine** (`/billing/preview/`, `/billing/run/`) |  Yes |  Yes |  No (403) |  Redirect (302) |
| **Review Queue** (`/billing/review/`) |  Yes |  Yes |  No (403) |  Redirect (302) |
| **Record Payment** (`/payments/invoice/<id>/new/`) |  Yes |  Yes |  No (403) |  Redirect (302) |
| **Settlement Ledger** (`/payments/`, `/payments/outstanding/`) |  Yes |  Yes |  No (403) |  Redirect (302) |
| **Catalog & Pricing Setup** (`/catalog/`) |  Yes |  Yes |  No (403) |  Redirect (302) |
| **Staff User Management** (`/accounts/staff/`) |  Yes |  No (403) |  No (403) |  Redirect (302) |
| **Customer Portal** (`/portal/`) |  Yes |  Yes |  Yes (Own Data) |  Redirect (302) |

---

## 📁 Repository Structure

```text
TeamAurevia/
├── accounts/               # Custom User model, auth views, role guards, staff management
├── billing/                # Invoices, payments, Billing Integrity Engine, Review Queue
│   ├── engine.py           # Core validation & invoice generation algorithms
│   ├── payments.py         # Atomic payment recording & balance settlement
│   ├── payment_views.py    # Ledger, aging receivables, and record payment views
│   └── tests_*.py          # Comprehensive test suites for engine and payments
├── catalog/                # Products, variants, plans, tax rules, discounts, templates
├── config/                 # Django settings, root URLs, role redirector
├── docs/                   # Architectural notes and pitch collateral
│   └── PITCH.md            # Hackathon pitch script and slide presentation outline
├── portal/                 # Customer self-service views
├── reports/                # Executive analytics, services, aggregation queries
│   ├── services.py         # MRR calculation, receivables aging, chart data
│   ├── views.py            # Dashboard and CSV export summary
│   └── tests.py            # Financial and metric mathematical verification tests
├── subscriptions/          # Contract lifecycle, quotation-to-subscription workflows
├── templates/              # Bootstrap 5 responsive templates
│   ├── accounts/           # Auth and staff administration
│   ├── base.html           # Core layout with navigation and alerts
│   ├── billing/            # Billing run preview, execution, and review queue
│   ├── payments/           # Payment settlement and aging screens
│   ├── reports/            # Executive dashboard and summary table
│   └── subscriptions/      # Subscription registry and detail pages
├── perf_check.py           # Latency SLO benchmark tester
├── seed.py                 # Deterministic high-volume dataset generator
├── manage.py
└── requirements.txt
```

---

## ⚡ Performance & Scale

SubSentry is engineered to adhere to strict corporate Service Level Objectives (SLOs):
- **Target Response Time:** `< 2.0 seconds` for all screens with 5,000+ active subscriptions.
- **Actual Benchmark Performance:**
  - Executive Dashboard: `~0.17 seconds`
  - Plan Revenue Summary: `~0.03 seconds`
  - Paid vs. Outstanding Aging: `~0.08 seconds`
  - Subscription Registry: `~0.05 seconds`

*(Verified via `python perf_check.py` on standard dual-core development machines)*

---

## 📸 Interface Preview

*(Screenshots will be captured during live demonstration)*
- **Executive Revenue Control Tower:** Real-time KPI cards for MRR, Collected Receivables, Aging Overdue, and Revenue at Risk.
- **Billing Run Preview & Review Queue:** Visual pre-flight check showing exactly which contracts are ready for billing and which require remediation.
- **Receivables Ledger:** Tabbed breakdown of Paid vs Outstanding balances with instant overdue aging indicators.

---

## 🛑 Out of Scope (By Design)

To maintain focus on core billing integrity and enterprise scale during the hackathon, the following items are purposefully out of scope:
- Live external payment gateway integration (Stripe, Razorpay API calls).
- Binary PDF generation (HTML/CSS browser print-ready invoices used instead).
- Mid-cycle proration calculation algorithms.
- Multi-currency conversions (all values standardized in INR - ₹).

---

## 👥 The Team

| Role | Owner | Focus Area |
| :--- | :--- | :--- |
| **P1 (Team Lead)** | **Suhani Kumari** | Architecture, Data Models, Subscription Lifecycle, Billing Integrity Engine |
| **P2** | Team Aurevia | Catalog Management, Product Variants, Plan Rules, Pricing Engine |
| **P3** | Team Aurevia | Customer Portal, Invoicing UI, Responsive Layouts |
| **P4** | Team Aurevia | Payment Settlement, Financial Analytics Dashboard, Seed Engine, Pitch & Benchmarks |

## Live demo
https://YOUR-APP.onrender.com

Logins: admin@subsentry.test / Admin@12345, staff@subsentry.test / Staff@12345, demo@subsentry.test / Demo@12345

