"""Invoice validation rules for LedgerPulse."""

from __future__ import annotations

from .currency import SUPPORTED_CURRENCIES
from .models import Invoice
from .pricing import MAX_DISCOUNT_BPS


class ValidationError(ValueError):
    """Raised when an invoice fails domain validation."""


def validate_invoice(invoice: Invoice) -> list[str]:
    """Return a list of validation error messages for an invoice."""
    errors: list[str] = []
    if not invoice.invoice_id.strip():
        errors.append("invoice_id must be non-empty")
    if not invoice.customer_id.strip():
        errors.append("customer_id must be non-empty")
    if invoice.currency not in SUPPORTED_CURRENCIES:
        errors.append(f"unsupported currency: {invoice.currency}")
    if not invoice.items:
        errors.append("invoice must contain at least one line item")
    if not (0 <= invoice.discount_bps <= MAX_DISCOUNT_BPS):
        errors.append(f"discount_bps must be between 0 and {MAX_DISCOUNT_BPS}")
    for idx, item in enumerate(invoice.items):
        if item.quantity <= 0:
            errors.append(f"item[{idx}].quantity must be positive")
        if item.unit_price_cents < 0:
            errors.append(f"item[{idx}].unit_price_cents must be non-negative")
    return errors


def require_valid_invoice(invoice: Invoice) -> None:
    """Validate an invoice and raise ValidationError if any rule fails."""
    errors = validate_invoice(invoice)
    if errors:
        raise ValidationError("; ".join(errors))
