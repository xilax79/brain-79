"""Tax calculation rules for LedgerPulse."""

from __future__ import annotations

from .currency import round_half_even
from .models import Invoice, LineItem

DEFAULT_TAX_BPS: int = 800
TAX_EXEMPT_SKUS: frozenset[str] = frozenset({"EXEMPT-EDU", "EXEMPT-NPO"})


def calculate_line_tax(item: LineItem, *, default_bps: int = DEFAULT_TAX_BPS) -> int:
    """Compute tax in cents for a single line item."""
    if item.sku in TAX_EXEMPT_SKUS:
        return 0
    rate = item.tax_rate_bps if item.tax_rate_bps > 0 else default_bps
    line_total = item.quantity * item.unit_price_cents
    return round_half_even((line_total * rate) / 10_000)


def calculate_invoice_tax(invoice: Invoice) -> int:
    """Compute total tax in cents across all line items on an invoice."""
    return sum(calculate_line_tax(item) for item in invoice.items)
