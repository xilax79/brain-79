import assert from "node:assert/strict";
import test from "node:test";

import {
  REPORT_SCHEMA_VERSION,
  buildAuditDigest,
  formatCents,
  runCli,
  validateReportPayload,
} from "../src/reporter/index.mjs";

test("validateReportPayload accepts valid summary", () => {
  const payload = {
    schema_version: REPORT_SCHEMA_VERSION,
    currency: "USD",
    invoice_count: 2,
    debits_cents: 5000,
    credits_cents: 2500,
    net_receivable_cents: 2500,
  };
  const result = validateReportPayload(payload);
  assert.equal(result.valid, true);
  assert.deepEqual(result.errors, []);
});

test("buildAuditDigest and runCli render deterministic digest", () => {
  const payload = {
    schema_version: REPORT_SCHEMA_VERSION,
    currency: "USD",
    invoice_count: 1,
    debits_cents: 2410,
    credits_cents: 2410,
    net_receivable_cents: 0,
  };
  assert.equal(formatCents(2410), "USD 24.10");
  const digest = buildAuditDigest(payload);
  assert.equal(digest.ok, true);
  assert.equal(digest.digest, "[v1.0] invoices=1 net=USD 0.00");

  const cli = runCli([], { readInput: () => JSON.stringify(payload) });
  assert.equal(cli.exitCode, 0);
  assert.equal(cli.stdout, "[v1.0] invoices=1 net=USD 0.00\n");
});
