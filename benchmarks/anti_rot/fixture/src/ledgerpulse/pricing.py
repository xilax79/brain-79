"""Subtotal, discount, and invoice total calculations."""

from __future__ import annotations

from .currency import round_half_even
from .models import Invoice, LineItem
from .tax import calculate_invoice_tax

MAX_DISCOUNT_BPS: int = 5000


def calculate_subtotal(items: list[LineItem]) -> int:
    """Return the pre-tax, pre-discount subtotal in cents."""
    return sum(item.quantity * item.unit_price_cents for item in items)


def apply_discount(subtotal_cents: int, discount_bps: int) -> int:
    """Return the discounted subtotal in cents, clamped to MAX_DISCOUNT_BPS."""
    clamped_bps = max(0, min(discount_bps, MAX_DISCOUNT_BPS))
    discount_amount = round_half_even((subtotal_cents * clamped_bps) / 10_000)
    return subtotal_cents - discount_amount


def compute_invoice_total(invoice: Invoice) -> int:
    """Compute the final invoice total in cents (discounted subtotal + tax)."""
    subtotal = calculate_subtotal(invoice.items)
    discounted = apply_discount(subtotal, invoice.discount_bps)
    return discounted + calculate_invoice_tax(invoice)
