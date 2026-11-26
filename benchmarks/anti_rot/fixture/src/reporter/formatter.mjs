/** Formatting utilities for LedgerPulse summary reports. */

/**
 * Format integer cents into a decimal currency string.
 * @param {number} cents
 * @param {string} currency
 * @returns {string}
 */
export function formatCents(cents, currency = "USD") {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(Math.trunc(cents));
  const whole = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, "0");
  return `${currency} ${sign}${whole}.${frac}`;
}

/**
 * Render a single-line summary string from a validated ledger summary.
 * @param {Record<string, any>} summary
 * @returns {string}
 */
export function formatSummaryLine(summary) {
  const cur = String(summary.currency ?? "USD");
  const net = formatCents(Number(summary.net_receivable_cents ?? 0), cur);
  return `invoices=${summary.invoice_count} net=${net}`;
}
