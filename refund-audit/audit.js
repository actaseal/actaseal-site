// Page glue for refund_audit_sandbox.html. No inline script (CSP is script-src 'self').
// The audit itself is the product's own Python (actaseal/reports/browser_audit.py), run in this tab by
// Pyodide from actaseal_audit_bundle/. Nothing is uploaded; cell text is only ever set as textContent.
const $ = (id) => document.getElementById(id);
const BUNDLE = "actaseal_audit_bundle/";
let pyodideReady = null;
let runAudit = null;
let detectCurrencies = null;
let last = null;

const COMMON = ["INR", "USD", "EUR", "GBP", "AED", "SGD", "AUD", "CAD"];

function setCurrencies(found) {
  const select = $("f-currency");
  const chosen = found.length ? found : COMMON;
  select.replaceChildren();
  for (const code of chosen) {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = code;
    select.appendChild(option);
  }
  select.value = chosen[0];
}
setCurrencies([]);

const ANY_APPROVER = "Anyone, if an approval is recorded";
const COMMON_ROLES = ["support_lead", "team_lead", "manager", "finance_lead", "admin"];

function setRoles(found) {
  const select = $("f-role");
  select.replaceChildren();
  const seen = new Set(found.map((r) => r.toLowerCase()));
  const extra = COMMON_ROLES.filter((r) => !seen.has(r));
  for (const [value, label] of [["", ANY_APPROVER], ...found.map((r) => [r, r]), ...extra.map((r) => [r, r])]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
  }
  select.value = found.length === 1 ? found[0] : "";
}
setRoles([]);

async function pickCurrencyFrom(bytes, name) {
  const pyodide = await pyodideReady;
  const out = JSON.parse(detectCurrencies(pyodide.toPy(bytes), name));
  if (out.ok) {
    setCurrencies(out.currencies);
    setRoles(out.approver_roles);
    if (out.currencies.length > 1) {
      setStatus("This file has more than one currency. Audit one at a time: pick the one your rule is for.");
    }
  }
}

function setStatus(text) { $("status").textContent = text; }

function showError(text) {
  const el = $("error");
  el.textContent = text;
  el.hidden = !text;
}

async function initPyodide() {
  setStatus("Loading the audit engine into this tab...");
  const pyodide = await loadPyodide();
  await pyodide.loadPackage("cryptography");
  const manifest = await (await fetch(BUNDLE + "manifest.json")).json();
  for (const rel of manifest.files) {
    const source = await (await fetch(BUNDLE + rel)).text();
    const dir = "/bundle/" + rel.split("/").slice(0, -1).join("/");
    pyodide.FS.mkdirTree(dir);
    pyodide.FS.writeFile("/bundle/" + rel, source);
  }
  pyodide.runPython(`
import sys, json
if "/bundle" not in sys.path:
    sys.path.insert(0, "/bundle")
from actaseal.reports.browser_audit import run_browser_audit, rules_from_fields, currencies_in

def detect(actions, actions_name):
    return json.dumps(currencies_in(bytes(actions), actions_name))

def run(actions, actions_name, payments, fields, notes):
    try:
        rules = rules_from_fields(**dict(fields))
    except ValueError as exc:
        return json.dumps({"ok": False, "code": "AUDIT_BAD_RULE", "message": str(exc)})
    out = run_browser_audit(bytes(actions), actions_name, rules, "rules.csv",
                            payments=bytes(payments) if payments else None,
                            credit_notes=bytes(notes) if notes else None)
    return json.dumps(out)
`);
  runAudit = pyodide.globals.get("run");
  detectCurrencies = pyodide.globals.get("detect");
  return pyodide;
}

function table(el, head, rows) {
  el.replaceChildren();
  const thead = el.createTHead().insertRow();
  for (const h of head) { const th = document.createElement("th"); th.textContent = h; thead.appendChild(th); }
  const tbody = el.createTBody();
  for (const r of rows) {
    const tr = tbody.insertRow();
    for (const c of r) tr.insertCell().textContent = c;
  }
}

const REASONS = {
  NO_APPROVAL_RECORDED: "No approval recorded",
  AMOUNT_ABOVE_HARD_BLOCK: "Above the never-refund limit",
  APPROVER_ROLE_MISMATCH: "Approved by the wrong role",
};

const CHECK_TITLES = {
  DUPLICATE_REFUND_ON_ORDER: "More than one refund on the same order",
  REFUND_EXCEEDS_ORDER: "Refunded more than the order was worth",
  REPEAT_CLAIMANT: "Same customer, refunded again and again",
  REFUND_AFTER_WINDOW: "Refunded after the return window",
  REFUND_PAID_LATE: "Owed to a customer: paid later than your rules allow",
  REFUND_NOT_PAID: "Owed to a customer: accepted and still not paid",
  REFUND_WITHOUT_CREDIT_NOTE: "Refunded with no GST credit note",
};

function render(out) {
  const report = out.report;
  const summary = $("summary");
  summary.replaceChildren();
  for (const line of out.summary_lines.filter((l) => l.startsWith("- "))) {
    const li = document.createElement("li");
    li.textContent = line.slice(2);
    summary.appendChild(li);
  }
  if (out.joined) {
    const li = document.createElement("li");
    li.textContent = `Payments file: ${out.joined.joined} of ${out.joined.refunds} refunds matched an order` +
      (out.joined.payment_not_in_file ? ` (${out.joined.payment_not_in_file} payments not in that file)` : "") + ".";
    summary.appendChild(li);
  }
  const outside = report.rows.filter((r) => r.verdict === "OUTSIDE_AUTHORITY");
  $("outside-title").textContent = `Broke the refund rule (${outside.length})`;
  table($("outside"), ["Row", "Refund", "Amount", "Reason", "Why"],
    outside.map((r) => [r.row, r.action_id, `${r.amount} ${r.currency}`, REASONS[r.reason_code] || r.reason_code, r.explanation]));
  const found = (report.refund_checks && report.refund_checks.findings) || [];
  $("cross-title").textContent = `Problems across orders and customers (${found.length})`;
  table($("cross"), ["Problem", "Order or customer", "Refunds", "Money at issue", "Why"],
    found.map((f) => [CHECK_TITLES[f.code] || f.code, f.order_id || f.customer_id || "",
      f.action_ids.slice(0, 20).join(", "), `${f.currency} ${f.amount_at_issue}`, f.why]));
  $("notice").textContent = report.notice;
  $("result").hidden = false;
}

function fields() {
  return {
    currency: $("f-currency").value, auto_allow_max: $("f-auto").value,
    approval_required_above: $("f-approval").value, hard_block_above: $("f-hard").value,
    approver_role: $("f-role").value, refund_window_days: $("f-days").value,
    refund_pay_within_days: $("f-pay").value,
  };
}

async function bytesOf(file) { return new Uint8Array(await file.arrayBuffer()); }

async function run(actionsBytes, name, sampleNotes) {
  showError("");
  $("result").hidden = true;
  const pyodide = await pyodideReady;
  const pay = $("payments-file").files[0];
  const payments = pay ? await bytesOf(pay) : null;
  const cn = $("notes-file").files[0];
  const notes = sampleNotes || (cn ? await bytesOf(cn) : null);
  const out = JSON.parse(runAudit(pyodide.toPy(actionsBytes), name, payments && pyodide.toPy(payments),
    pyodide.toPy(fields()), notes && pyodide.toPy(notes)));
  if (!out.ok) { showError(`${out.code}: ${out.message}`); return; }
  last = out;
  render(out);
}

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

$("refunds-file").addEventListener("change", async () => {
  const file = $("refunds-file").files[0];
  if (file) await pickCurrencyFrom(await bytesOf(file), file.name);
});
$("run-btn").addEventListener("click", async () => {
  const file = $("refunds-file").files[0];
  if (!file) { showError("Choose your refunds file first."); return; }
  await run(await bytesOf(file), file.name);
});
$("sample-btn").addEventListener("click", async () => {
  const text = await (await fetch("sample/refunds.csv")).arrayBuffer();
  const notes = await (await fetch("sample/credit_notes.csv")).arrayBuffer();
  setStatus("Showing made-up sample data, not a real company.");
  const bytes = new Uint8Array(text);
  await pickCurrencyFrom(bytes, "refunds.csv");
  await run(bytes, "refunds.csv", new Uint8Array(notes));
});
$("dl-csv").addEventListener("click", () => last && download("refund_audit_rows.csv", last.csv, "text/csv"));
$("dl-md").addEventListener("click", () => last && download("refund_audit_report.md", last.markdown, "text/markdown"));

pyodideReady = initPyodide().then((p) => {
  setStatus("Ready. Your file stays in this tab.");
  $("run-btn").disabled = false;
  $("run-btn").textContent = "Run audit";
  return p;
}).catch((err) => {
  setStatus("");
  showError("The audit engine could not load: " + err.message);
  throw err;
});
