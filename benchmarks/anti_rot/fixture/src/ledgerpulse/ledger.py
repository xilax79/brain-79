"""Double-entry-inspired ledger posting and payment tracking."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Invoice, InvoiceStatus
from .pricing import compute_invoice_total
from .validation import ValidationError, require_valid_invoice


@dataclass(frozen=True)
class LedgerEntry:
    """Immutable ledger posting or payment record."""

    entry_id: str
    invoice_id: str
    customer_id: str
    kind: str
    amount_cents: int
    note: str = ""


class Ledger:
    """In-memory invoice and payment ledger."""

    def __init__(self) -> None:
        self._invoices: dict[str, Invoice] = {}
        self._entries: list[LedgerEntry] = []

    @property
    def entries(self) -> list[LedgerEntry]:
        """Return a shallow copy of recorded ledger entries."""
        return list(self._entries)

    @property
    def invoices(self) -> dict[str, Invoice]:
        """Return a shallow copy of tracked invoices by ID."""
        return dict(self._invoices)

    def post_invoice(self, invoice: Invoice) -> LedgerEntry:
        """Validate and post an invoice, recording a debit entry."""
        require_valid_invoice(invoice)
        if invoice.invoice_id in self._invoices:
            raise ValidationError(f"duplicate invoice_id: {invoice.invoice_id}")
        total = compute_invoice_total(invoice)
        invoice.status = InvoiceStatus.POSTED
        self._invoices[invoice.invoice_id] = invoice
        entry = LedgerEntry(
            entry_id=f"E-{len(self._entries) + 1:04d}",
            invoice_id=invoice.invoice_id,
            customer_id=invoice.customer_id,
            kind="debit",
            amount_cents=total,
        )
        self._entries.append(entry)
        return entry

    def record_payment(self, invoice_id: str, amount_cents: int) -> LedgerEntry:
        """Record a customer payment against a posted invoice."""
        if amount_cents <= 0:
            raise ValidationError("payment amount_cents must be positive")
        invoice = self._invoices.get(invoice_id)
        if invoice is None:
            raise ValidationError(f"unknown invoice_id: {invoice_id}")
        if invoice.status == InvoiceStatus.VOID:
            raise ValidationError(f"cannot pay void invoice: {invoice_id}")
        entry = LedgerEntry(
            entry_id=f"E-{len(self._entries) + 1:04d}",
            invoice_id=invoice_id,
            customer_id=invoice.customer_id,
            kind="credit",
            amount_cents=amount_cents,
        )
        self._entries.append(entry)
        if self.invoice_balance(invoice_id) <= 0:
            invoice.status = InvoiceStatus.PAID
        return entry

    def invoice_balance(self, invoice_id: str) -> int:
        """Return remaining unpaid balance in cents for an invoice."""
        debits = sum(e.amount_cents for e in self._entries if e.invoice_id == invoice_id and e.kind == "debit")
        credits = sum(e.amount_cents for e in self._entries if e.invoice_id == invoice_id and e.kind == "credit")
        return debits - credits

    def balance_for_customer(self, customer_id: str) -> int:
        """Return net receivable balance in cents for a customer."""
        debits = sum(e.amount_cents for e in self._entries if e.customer_id == customer_id and e.kind == "debit")
        credits = sum(e.amount_cents for e in self._entries if e.customer_id == customer_id and e.kind == "credit")
        return debits - credits

    def trial_balance(self) -> dict[str, int]:
        """Return total debits, total credits, and net receivable."""
        debits = sum(e.amount_cents for e in self._entries if e.kind == "debit")
        credits = sum(e.amount_cents for e in self._entries if e.kind == "credit")
        return {"debits": debits, "credits": credits, "net_receivable": debits - credits}
