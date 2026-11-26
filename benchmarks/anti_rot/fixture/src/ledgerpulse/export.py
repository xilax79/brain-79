"""Structured JSON-serializable export helpers for LedgerPulse."""

from __future__ import annotations

from .currency import DEFAULT_CURRENCY
from .ledger import Ledger
from .models import Invoice
from .pricing import compute_invoice_total

SCHEMA_VERSION: str = "1.0"


def invoice_to_dict(invoice: Invoice) -> dict[str, object]:
    """Serialize an Invoice into a JSON-compatible dictionary."""
    return {
        "invoice_id": invoice.invoice_id,
        "customer_id": invoice.customer_id,
        "status": invoice.status.value,
        "currency": invoice.currency,
        "discount_bps": invoice.discount_bps,
        "total_cents": compute_invoice_total(invoice),
        "item_count": len(invoice.items),
    }


def export_ledger_summary(
    ledger: Ledger,
    *,
    currency: str = DEFAULT_CURRENCY,
) -> dict[str, object]:
    """Build a summary payload consumable by the JS reporter."""
    tb = ledger.trial_balance()
    return {
        "schema_version": SCHEMA_VERSION,
        "currency": currency,
        "invoice_count": len(ledger.invoices),
        "debits_cents": tb["debits"],
        "credits_cents": tb["credits"],
        "net_receivable_cents": tb["net_receivable"],
    }
