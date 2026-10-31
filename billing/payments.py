from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Invoice, Payment


def record_payment(invoice, method, amount, payment_date=None, note='', user=None) -> Payment:
    """
    Records a payment against a confirmed invoice inside an atomic transaction.
    - Rejects if invoice is not in Confirmed status.
    - Rejects if amount <= 0 or amount > invoice.balance.
    - Creates the Payment record.
    - Updates invoice.amount_paid.
    - Transitions invoice status to Paid when balance reaches 0.
    """
    if payment_date is None:
        payment_date = timezone.now().date()

    if isinstance(amount, (int, float, str)):
        amount = Decimal(str(amount))

    with transaction.atomic():
        # Reload invoice with a lock if possible, or fresh from db
        inv = Invoice.objects.select_for_update().get(pk=invoice.pk)

        # 1. Invoice status check
        if inv.status != Invoice.STATUS_CONFIRMED:
            raise ValidationError(
                f"Payments can only be recorded on Confirmed invoices. Current status is '{inv.get_status_display()}'."
            )

        # 2. Amount > 0 check
        if amount <= Decimal('0.00'):
            raise ValidationError("Payment amount must be greater than zero.")

        # 3. Overpayment check
        balance = inv.balance
        if amount > balance:
            raise ValidationError(
                f"Payment amount (${amount:.2f}) exceeds current invoice balance (${balance:.2f})."
            )

        # 4. Create Payment
        payment = Payment.objects.create(
            invoice=inv,
            method=method,
            amount=amount,
            payment_date=payment_date,
            note=note,
            recorded_by=user,
        )

        # 5. Update invoice amount_paid and status
        inv.amount_paid = (inv.amount_paid or Decimal('0.00')) + amount
        if inv.balance <= Decimal('0.00'):
            inv.status = Invoice.STATUS_PAID

        inv.save(update_fields=['amount_paid', 'status'])

        return payment

