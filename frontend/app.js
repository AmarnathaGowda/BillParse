const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const statusEl = document.getElementById("status");
const table = document.getElementById("results-table");
const tbody = table.querySelector("tbody");
const downloadBtn = document.getElementById("download-btn");
const resetBtn = document.getElementById("reset-btn");

let rowCount = 0;

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

  setStatus(`Extracting ${files.length} file(s)…`, "loading");
  table.hidden = false;

  const formData = new FormData();
  for (const file of files) formData.append("files", file);

  try {
    const response = await fetch("/api/extract", { method: "POST", body: formData });
    if (!response.ok) throw new Error(`Server error (${response.status})`);
    const data = await response.json();
    for (const row of data.results) addRow(row);
    setStatus(`Done. Processed ${files.length} file(s).`, "success");
    downloadBtn.disabled = false;
    resetBtn.disabled = false;
  } catch (err) {
    setStatus(`Upload failed: ${err.message}`, "error");
  } finally {
    fileInput.value = "";
  }
}

function addRow(row) {
  rowCount += 1;
  const tr = document.createElement("tr");
  tr.className = `row-${row.status}`;

  const usage = row.usage_amount != null ? `${row.usage_amount} ${row.usage_unit ?? ""}`.trim() : "—";
  const period =
    row.billing_period_start || row.billing_period_end
      ? `${row.billing_period_start ?? "?"} → ${row.billing_period_end ?? "?"}`
      : "—";
  const statusLabel = row.status === "ok" ? "OK" : row.error_message ?? row.status;

  tr.innerHTML = `
    <td>${escapeHtml(row.source_filename)}</td>
    <td>${escapeHtml(row.vendor_name ?? "—")}</td>
    <td>${escapeHtml(row.invoice_date ?? "—")}</td>
    <td>${escapeHtml(row.service_address ?? "—")}</td>
    <td>${escapeHtml(row.utility_type ?? "—")}</td>
    <td>${escapeHtml(usage)}</td>
    <td>${escapeHtml(period)}</td>
    <td>${escapeHtml(row.detected_language ?? "—")}</td>
    <td>${escapeHtml(row.confidence ?? "—")}</td>
    <td>${escapeHtml(statusLabel)}</td>
  `;
  tbody.appendChild(tr);
}

function setStatus(message, kind) {
  statusEl.textContent = message;
  statusEl.className = `status status-${kind}`;
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
  table.hidden = true;
  downloadBtn.disabled = true;
  resetBtn.disabled = true;
  setStatus("Results cleared.", "success");
  rowCount = 0;
});
