# mypy: ignore-errors
"""Unit tests for LedgerPulse Python core."""

from __future__ import annotations

import pytest

from ledgerpulse import (
    Invoice,
    InvoiceStatus,
    Ledger,
    LineItem,
    Money,
    ValidationError,
    compute_invoice_total,
    export_ledger_summary,
    format_money,
    reconcile_payments,
)


def _sample_invoice(invoice_id: str = "INV-001") -> Invoice:
    return Invoice(
        invoice_id=invoice_id,
        customer_id="CUST-1",
        items=[
            LineItem(sku="WIDGET-A", description="Widget A", quantity=2, unit_price_cents=1000),
            LineItem(sku="EXEMPT-EDU", description="Edu license", quantity=1, unit_price_cents=500),
        ],
        discount_bps=1000,
    )


def test_compute_invoice_total_and_format_money() -> None:
    inv = _sample_invoice()
    # Subtotal = 2500, 10% discount = 2250, tax on 2000 @ 8% = 160 (EXEMPT-EDU = 0) -> 2410
    assert compute_invoice_total(inv) == 2410
    assert format_money(Money(2410, "USD")) == "USD 24.10"


def test_ledger_post_payment_and_reconcile() -> None:
    ledger = Ledger()
    inv = _sample_invoice()
    ledger.post_invoice(inv)
    assert inv.status == InvoiceStatus.POSTED
    assert ledger.balance_for_customer("CUST-1") == 2410

    ledger.record_payment("INV-001", 2410)
    assert inv.status == InvoiceStatus.PAID
    assert ledger.balance_for_customer("CUST-1") == 0

    report = reconcile_payments(
        ledger,
        [{"txn_id": "TXN-1", "invoice_id": "INV-001", "amount_cents": 2410}],
    )
    assert report.is_clean
    assert len(report.matched_ids) == 1

    summary = export_ledger_summary(ledger)
    assert summary["invoice_count"] == 1
    assert summary["net_receivable_cents"] == 0


def test_validation_rejects_empty_invoice() -> None:
    ledger = Ledger()
    bad = Invoice(invoice_id="", customer_id="CUST-1", items=[])
    with pytest.raises(ValidationError):
        ledger.post_invoice(bad)
