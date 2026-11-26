/** Schema validation for LedgerPulse summary payloads. */

export const REPORT_SCHEMA_VERSION = "1.0";

export const REQUIRED_SUMMARY_FIELDS = [
  "schema_version",
  "currency",
  "invoice_count",
  "debits_cents",
  "credits_cents",
  "net_receivable_cents",
];

/**
 * Validate a ledger summary payload.
 * @param {Record<string, unknown>} payload
 * @returns {{ valid: boolean, errors: string[] }}
 */
export function validateReportPayload(payload) {
  const errors = [];
  if (!payload || typeof payload !== "object") {
    return { valid: false, errors: ["payload must be an object"] };
  }
  for (const field of REQUIRED_SUMMARY_FIELDS) {
    if (!(field in payload)) {
      errors.push(`missing required field: ${field}`);
    }
  }
  if (payload.schema_version !== REPORT_SCHEMA_VERSION) {
    errors.push(`unsupported schema_version: ${String(payload.schema_version)}`);
  }
  if (typeof payload.invoice_count !== "number" || payload.invoice_count < 0) {
    errors.push("invoice_count must be a non-negative number");
  }
  return { valid: errors.length === 0, errors };
}
