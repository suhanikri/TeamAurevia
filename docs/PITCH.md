# SubSentry - Hackathon Pitch Deck & Demo Guide

> **Tagline:** *"Every subscription billed once, billed right."*  
> **Team:** Team Aurevia (Lead: Suhani Kumari)  
> **Submission Date:** October 31, 2026

---

## ⏱️ 3-Minute Live Pitch Script

### [0:00 - 0:30] Hook & Problem
"Good afternoon, judges. 

If you ask any SaaS CFO what keeps them up at night, it isn't winning the next customer—it is **billing leakage and double-billing**. 

In high-volume recurring subscription businesses, billing engines break down. A network timeout happens, a job retries, and suddenly a customer is billed twice for the same month. Or worse, subscriptions quietly bill against expired plans, exhausted discounts, or without legally required tax configurations. 

This results in chargebacks, damaged customer trust, and hours of finance team reconciliation."

### [0:30 - 1:15] The Solution & The Billing Integrity Engine
"That is why we built **SubSentry**.

SubSentry is an enterprise subscription billing control platform anchored by our proprietary **Billing Integrity Engine**. 

Instead of blindly firing invoices, SubSentry implements a deterministic, pre-flight gatekeeper. At the database layer, we enforce a strict `UniqueConstraint` on the subscription and billing period. A customer **can never be billed twice for the same cycle**—period.

Before any invoice is committed, our engine evaluates contract eligibility: Is the plan active? Are tax rules present? Is the discount valid? If anything is irregular, SubSentry doesn't crash or silently charge the user—it routes the subscription to an interactive **Review Queue** with exact root-cause diagnostics for billing operations."

### [1:15 - 2:15] Live Product Walkthrough
*(Switch screen to live browser)*

1. **Executive Dashboard (`/dashboard/`):**  
   "Here is our Executive Revenue Control Tower. Notice that despite having **5,000 active subscriptions** in the database, this entire screen loaded in **under 200 milliseconds**. We track real-time MRR normalized across daily, weekly, monthly, and yearly cycles. Notice our signature KPI: **Revenue at Risk**—which automatically calculates overdue receivables plus active contracts flagged in the Review Queue."

2. **The Review Queue in Action (`/billing/review/`):**  
   "Let's look at our Review Queue. We planted 11 difficult edge cases: contracts with expired plans, exhausted founder discounts, paused subscriptions, and missing tax definitions. SubSentry caught all 11, shielding Brightloop Software from erroneous charges."

3. **Billing Run Execution (`/billing/preview/`):**  
   "When staff executes a billing cycle, SubSentry provides a zero-risk preview first, then atomically processes the clean contracts, updating invoice sequences and advancing next billing dates."

4. **Receivables Aging (`/payments/outstanding/`):**  
   "Finally, our Settlement Ledger tracks invoices by aging days with one-click payment settlement and instant CSV exports."

### [2:15 - 3:00] Business Impact, Tech Architecture & Closing
"Under the hood, SubSentry is powered by pure, robust engineering: Django with advanced database-level aggregations, transactional locks, zero bulky node dependencies, and full test coverage across 40+ unit and integration test cases.

Our automated performance benchmark (`perf_check.py`) proves every core view responds in **under 0.2 seconds** at scale.

SubSentry guarantees that your recurring revenue is protected, your finance ops are automated, and every subscription is billed once, and billed right.

Thank you! We welcome your questions."

---

## 🛟 1-Minute Backup Talk Track (If Demo or Screen Breaks)

*(Use this if there is a projector glitch, WiFi drops, or local server stoppage)*

"While we bring the display back up, let me walk you through the core engineering breakthrough of SubSentry:

Most billing systems treat recurring runs as simple cron scripts that generate invoices sequentially. That’s how duplicate charges and accounting errors happen. 

In SubSentry, we built a **two-phase deterministic commit model**:
- **Phase 1: Pre-Flight Evaluation:** We run an in-memory inspection of plan validity, line taxes, and discount quotas.
- **Phase 2: Atomic State Machine:** When an invoice is created, it takes an atomic database lock with a hard unique constraint on the contract period. 

If a contract has an issue—like an expired plan—it is routed into an operational Review Queue without halting the batch. 

In our test suite, we validated this across 5,000 high-scale subscriptions and proved a sub-0.2 second response time across all executive dashboards. 

Every subscription is billed once, and billed right."

---

## 📊 7-Slide Pitch Presentation Outline

### Slide 1: Cover & Vision
- **Title:** SubSentry
- **Subtitle:** Enterprise Subscription Management & Deterministic Billing Integrity
- **Tagline:** *"Every subscription billed once, billed right."*
- **Team:** Team Aurevia (P1 Lead: Suhani Kumari)

### Slide 2: The $50M SaaS Problem
- **Double Billing:** Retried payment cron jobs accidentally charging customers twice.
- **Silent Revenue Leakage:** Subscriptions continuing on expired promotional discounts or obsolete pricing tiers.
- **Tax Non-Compliance:** Unbilled tax liabilities causing regulatory headaches.
- **Operational Drag:** Manual spreadsheet audits between billing and accounts receivable.

### Slide 3: The SubSentry Solution
- **Deterministic Gatekeeper:** The Billing Integrity Engine acts as an automated audit layer before invoice generation.
- **The Double-Billing Barrier:** Hard database `UniqueConstraint(subscription, period_start)`.
- **Review Queue:** Automatic quarantine and classification of invalid contracts.
- **Unified Control Tower:** Real-time visibility into MRR, Aging Receivables, and Revenue at Risk.

### Slide 4: Billing Integrity Engine Architecture
- **Evaluation Pipeline:**
  1. Status Guard: Contract must be Active (Paused/Closed rejected).
  2. Plan Guard: Date must fall inside plan validity window.
  3. Tax Compliance: Every product line must have an active tax rule.
  4. Quota Check: Discounts verified for expiration and usage limit.
  5. Idempotency Check: Existing active invoices block duplicates.
- **Outcomes:** `Ready` -> Generated atomically | `Invalid` -> Flagged to Review Queue.

### Slide 5: Live Demonstration Workflow
- **Screen 1:** Executive Dashboard (`/dashboard/`) — Instant KPIs, Chart.js breakdown, sub-200ms load.
- **Screen 2:** Billing Preview & Review Queue (`/billing/preview/`, `/billing/review/`) — 11 planted edge cases caught.
- **Screen 3:** Settlement & Aging (`/payments/outstanding/`) — One-click payment recording with automatic balance reconciliation.

### Slide 6: Engineering Rigor & Benchmark Proof
- **Database Scalability:** 5,000 subscriptions, 10,000 lines, 2,000 invoices generated in 8 seconds via bulk operations.
- **Performance:** 100% of endpoints pass corporate SLO (< 2.0s), averaging **0.05s** latency.
- **Quality Assurance:** 40+ unit and integration tests passing across all Django apps.

### Slide 7: Roadmap & Next Horizon
- **Payment Gateways:** Webhook synchronization with Stripe & Razorpay.
- **Smart Retries:** Automated dunning workflows for failed recurring cards.
- **Automated Remediation:** One-click bulk resolution in the Review Queue.
- **Multi-Currency:** Automated daily FX conversions for international enterprise contracts.

