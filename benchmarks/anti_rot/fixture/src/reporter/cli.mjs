/** Pure CLI helpers for LedgerPulse report verification. */

import { formatSummaryLine } from "./formatter.mjs";
import { validateReportPayload } from "./schema.mjs";

/**
 * Build a deterministic audit digest string from a summary payload.
 * @param {Record<string, any>} summary
 * @returns {{ ok: boolean, digest: string, errors: string[] }}
 */
export function buildAuditDigest(summary) {
  const check = validateReportPayload(summary);
  if (!check.valid) {
    return { ok: false, digest: "", errors: check.errors };
  }
  return {
    ok: true,
    digest: `[v${summary.schema_version}] ${formatSummaryLine(summary)}`,
    errors: [],
  };
}

/**
 * Execute reporter CLI logic against JSON string input.
 * @param {string[]} argv
 * @param {{ readInput?: () => string }} io
 * @returns {{ exitCode: number, stdout: string, stderr: string }}
 */
export function runCli(argv, io = {}) {
  if (argv.includes("--version")) {
    return { exitCode: 0, stdout: "ledgerpulse-reporter 0.1.0\n", stderr: "" };
  }
  const raw = io.readInput ? io.readInput() : "";
  if (!raw.trim()) {
    return { exitCode: 2, stdout: "", stderr: "empty input payload\n" };
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { exitCode: 2, stdout: "", stderr: "invalid JSON payload\n" };
  }
  const res = buildAuditDigest(parsed);
  if (!res.ok) {
    return { exitCode: 1, stdout: "", stderr: `${res.errors.join("; ")}\n` };
  }
  return { exitCode: 0, stdout: `${res.digest}\n`, stderr: "" };
}
