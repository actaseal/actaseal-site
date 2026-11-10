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

// "INR 25598" -> "INR 25,598" (Indian grouping for INR), for display only.
function money(text) {
  return String(text).replace(/\b([A-Z]{3}) (-?\d+(?:\.\d+)?)\b/g, (m, code, n) =>
    `${code} ${Number(n).toLocaleString(code === "INR" ? "en-IN" : "en-US", { maximumFractionDigits: 2 })}`);
}
let engineReady = false;

function showError(text) {
  const el = $("error");
  el.textContent = text;
  el.hidden = !text;
}

// Pyodide comes from a copy next to this page when one is there (pyodide/, for a deployment that
// must not call a CDN), otherwise from jsDelivr. The runtime, the cryptography package and the
// checker's own files all download at the same time instead of one after another.
const PYODIDE_LOCAL = "pyodide/";
const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

// Returns [base URL, loader file]. A local copy may be the classic pyodide.js or, from newer
// Pyodide releases, only the ES module pyodide.mjs; both are tried before the CDN.
async function pyodideSource() {
  for (const file of ["pyodide.js", "pyodide.mjs"]) {
    try {
      const r = await fetch(PYODIDE_LOCAL + file, { method: "HEAD" });
      if (r.ok) return [PYODIDE_LOCAL, file];
    } catch (_) { /* no local copy */ }
  }
  return [PYODIDE_CDN, "pyodide.js"];
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error("could not load " + src));
    document.head.appendChild(s);
  });
}

async function loadRuntime(base, file) {
  if (typeof loadPyodide !== "undefined") return loadPyodide;
  if (file.endsWith(".mjs")) return (await import(new URL(base + file, location.href).href)).loadPyodide;
  await loadScript(base + file);
  return loadPyodide;
}

async function fetchBundle() {
  const manifest = await (await fetch(BUNDLE + "manifest.json")).json();
  return Promise.all(manifest.files.map(async (rel) => {
    const r = await fetch(BUNDLE + rel);
    if (!r.ok) throw new Error("could not load " + rel);
    return [rel, await r.text()];
  }));
}

async function initPyodide() {
  setStatus("Loading the checker into this tab (step 1 of 3). The first time takes under a minute; after that it is cached.");
  const bundle = fetchBundle();
  const [base, file] = await pyodideSource();
  const load = await loadRuntime(base, file);
  const pyodide = await load({ indexURL: new URL(base, location.href).href });
  setStatus("Loading the checker into this tab (step 2 of 3): signature library.");
  const [files] = await Promise.all([bundle, pyodide.loadPackage("cryptography")]);
  setStatus("Loading the checker into this tab (step 3 of 3).");
  for (const [rel, source] of files) {
    pyodide.FS.mkdirTree("/bundle/" + rel.split("/").slice(0, -1).join("/"));
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
    fields = dict(fields)
    gst_rate = fields.pop("gst_rate", "")
    try:
        rules = rules_from_fields(**fields)
    except ValueError as exc:
        return json.dumps({"ok": False, "code": "AUDIT_BAD_RULE", "message": str(exc)})
    out = run_browser_audit(bytes(actions), actions_name, rules, "rules.csv",
                            payments=bytes(payments) if payments else None,
                            credit_notes=bytes(notes) if notes else None, gst_rate=gst_rate)
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
    li.textContent = money(line.slice(2));
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
    outside.map((r) => [r.row, r.action_id, money(`${r.currency} ${r.amount}`), REASONS[r.reason_code] || r.reason_code, r.explanation]));
  const found = (report.refund_checks && report.refund_checks.findings) || [];
  $("cross-title").textContent = `Problems across orders and customers (${found.length})`;
  table($("cross"), ["Problem", "Order or customer", "Refunds", "Money at issue", "Why"],
    found.map((f) => [CHECK_TITLES[f.code] || f.code, f.order_id || f.customer_id || "",
      f.action_ids.slice(0, 20).join(", "), money(`${f.currency} ${f.amount_at_issue}`), f.why]));
  $("dl-cn").hidden = !out.credit_note_drafts;
  $("notice").textContent = report.notice;
  $("result").hidden = false;
}

function fields() {
  return {
    currency: $("f-currency").value, auto_allow_max: $("f-auto").value,
    approval_required_above: $("f-approval").value, hard_block_above: $("f-hard").value,
    approver_role: $("f-role").value, refund_window_days: $("f-days").value,
    refund_pay_within_days: $("f-pay").value, gst_rate: $("f-gst").value,
  };
}

async function bytesOf(file) { return new Uint8Array(await file.arrayBuffer()); }

async function run(actionsBytes, name, sampleNotes) {
  showError("");
  $("result").hidden = true;
  if (!engineReady) setStatus("Still loading the checker; your result will show in a moment.");
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
function firm() { return $("f-firm").value.trim(); }
function withFirm(markdown) { return firm() ? `Prepared by ${firm()}.\n\n${markdown}` : markdown; }
$("f-firm").addEventListener("input", () => {
  $("prepared").textContent = firm() ? `Prepared by ${firm()}.` : "";
  $("prepared").hidden = !firm();
});
$("dl-md").addEventListener("click", () => last && download("refund_audit_report.md", withFirm(last.markdown), "text/markdown"));
// Only the summary lines go into the email, written by the person's own mail app; no file leaves this tab.
$("send-ca").addEventListener("click", () => {
  if (!last) return;
  const lines = [...$("summary").querySelectorAll("li")].map((li) => `- ${li.textContent}`);
  const body = ["Refund check summary (run in my browser, nothing uploaded):", "", ...lines, "",
    "The full report and rows are with me. The check: https://actaseal.com/refund-audit/"].join("\n");
  window.location.href = `mailto:?subject=${encodeURIComponent("Refund check: what it found")}&body=${encodeURIComponent(body)}`;
});
$("dl-cn").addEventListener("click", () => last && last.credit_note_drafts &&
  download("draft_credit_notes.csv", last.credit_note_drafts, "text/csv"));
// The browser's own print dialog saves the result as a PDF; print CSS hides everything but the result.
$("dl-pdf").addEventListener("click", () => last && window.print());

pyodideReady = initPyodide().then((p) => {
  engineReady = true;
  setStatus("Ready. Your file stays in this tab.");
  $("run-btn").disabled = false;
  $("run-btn").textContent = "Run audit";
  return p;
}).catch((err) => {
  setStatus("");
  showError("The audit engine could not load: " + err.message);
  throw err;
});
