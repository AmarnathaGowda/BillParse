const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const statusEl = document.getElementById("status");
const logPanel = document.getElementById("log-panel");
const logList = document.getElementById("log-list");
const table = document.getElementById("results-table");
const tbody = table.querySelector("tbody");
const downloadBtn = document.getElementById("download-btn");
const resetBtn = document.getElementById("reset-btn");

dropzone.addEventListener("click", () => fileInput.click());

dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));

dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener("change", () => handleFiles(fileInput.files));

async function handleFiles(fileList) {
  const files = Array.from(fileList);
  if (files.length === 0) return;

  table.hidden = false;
  logPanel.hidden = false;
  logList.innerHTML = "";
  logLine(`Starting extraction for ${files.length} file(s)…`);

  let succeeded = 0;
  let failed = 0;

  for (const file of files) {
    setStatus(`Processing ${file.name}…`, "loading");
    logLine(`${file.name}: extracting text and calling Claude…`);

    try {
      const row = await extractOne(file);
      addRow(row);
      if (row.status === "ok") {
        succeeded += 1;
        logLine(`${file.name}: done (confidence: ${row.confidence ?? "n/a"}).`);
      } else {
        failed += 1;
        logLine(`${file.name}: ${row.status} — ${row.error_message ?? "no details"}.`, "warn");
      }
    } catch (err) {
      failed += 1;
      logLine(`${file.name}: request failed — ${err.message}.`, "error");
    }
  }

  setStatus(`Done. ${succeeded} succeeded, ${failed} failed, out of ${files.length}.`, failed ? "error" : "success");
  downloadBtn.disabled = false;
  resetBtn.disabled = false;
  fileInput.value = "";
}

async function extractOne(file) {
  const formData = new FormData();
  formData.append("files", file);

  const response = await fetch("/api/extract", { method: "POST", body: formData });
  if (!response.ok) throw new Error(`Server error (${response.status})`);
  const data = await response.json();
  return data.results[0];
}

function addRow(row) {
  const tr = document.createElement("tr");
  tr.className = `row-${row.status}`;

  const usage = row.usage_amount != null ? `${row.usage_amount} ${row.usage_unit ?? ""}`.trim() : "—";
  const statusLabel = row.status === "ok" ? "OK" : row.error_message ?? row.status;

  tr.innerHTML = `
    <td>${escapeHtml(row.source_filename)}</td>
    <td>${escapeHtml(row.vendor_name ?? "—")}</td>
    <td>${dateCell(row.invoice_date)}</td>
    <td>${escapeHtml(row.service_address ?? "—")}</td>
    <td>${escapeHtml(row.utility_type ?? "—")}</td>
    <td>${escapeHtml(usage)}</td>
    <td>${dateCell(row.billing_period_start)}</td>
    <td>${dateCell(row.billing_period_end)}</td>
    <td>${escapeHtml(row.detected_language ?? "—")}</td>
    <td>${escapeHtml(row.confidence ?? "—")}</td>
    <td>${escapeHtml(statusLabel)}</td>
  `;
  tbody.appendChild(tr);
}

// Renders an ISO 8601 (YYYY-MM-DD) date as a readable label, with the raw
// value kept in a title attribute so the exact ISO string is one hover away.
function dateCell(isoDate) {
  if (!isoDate) return "—";
  const parsed = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return `<span title="Unparseable date value">${escapeHtml(isoDate)}</span>`;
  }
  const label = parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  return `<span title="${escapeHtml(isoDate)}">${escapeHtml(label)}</span>`;
}

function setStatus(message, kind) {
  statusEl.textContent = message;
  statusEl.className = `status status-${kind}`;
}

function logLine(message, level = "info") {
  const li = document.createElement("li");
  const timestamp = new Date().toLocaleTimeString();
  li.className = `log-${level}`;
  li.textContent = `[${timestamp}] ${message}`;
  logList.appendChild(li);
  logList.scrollTop = logList.scrollHeight;
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

downloadBtn.addEventListener("click", () => {
  window.location.href = "/api/export.csv";
});

resetBtn.addEventListener("click", async () => {
  await fetch("/api/reset", { method: "POST" });
  tbody.innerHTML = "";
  logList.innerHTML = "";
  table.hidden = true;
  logPanel.hidden = true;
  downloadBtn.disabled = true;
  resetBtn.disabled = true;
  setStatus("Results cleared.", "success");
});
