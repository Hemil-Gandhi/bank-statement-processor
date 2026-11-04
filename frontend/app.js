/* LedgerLens frontend — vanilla JS, no build step, no external calls. */
(() => {
  "use strict";

  const API = "/api";
  const MAX_FILE_MB = 25;
  const COLORS = [
    "#0f5c6b", "#d97706", "#2563eb", "#b91c1c", "#64748b",
    "#0e7490", "#a16207", "#475569", "#be123c", "#0369a1",
  ];

  const state = {
    info: null,
    categories: [],
    current: null,
    transactions: null,
    summary: null,
    history: [],
    selectedIds: new Set(),
    filters: {
      page: 1,
      page_size: 50,
      date_from: "",
      date_to: "",
      category: "",
      type: "",
      search: "",
      flagged_only: false,
      sort: "date_asc",
    },
    uploading: false,
    passwordResolver: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const esc = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

  const money = (value, currency = "INR") => {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    try {
      return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: currency || "INR",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(number);
    } catch {
      return `₹${number.toFixed(2)}`;
    }
  };

  const compactMoney = (value) => {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return "—";
    try {
      return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(number);
    } catch {
      return `₹${Math.round(number).toLocaleString("en-IN")}`;
    }
  };

  const number = (value) => Number(value || 0).toLocaleString("en-IN");
  const pct = (value) => `${Math.round(Number(value || 0) * 100)}%`;

  const parseDateOnly = (value) => {
    if (!value) return null;
    const date = new Date(`${value}T00:00:00`);
    return Number.isNaN(date.getTime()) ? null : date;
  };

  const formatDate = (value) => {
    const date = value instanceof Date ? value : parseDateOnly(value);
    if (!date) return "—";
    return date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  };

  const formatShortDate = (value) => {
    const date = parseDateOnly(value);
    if (!date) return "—";
    return date.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  };

  const formatDateTime = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString("en-IN", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  };

  const debounce = (fn, wait = 320) => {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  };

  function toast(title, message = "", type = "success") {
    const stack = $("#toast-stack");
    const node = document.createElement("div");
    node.className = `toast ${type}`;
    node.innerHTML = `<strong>${esc(title)}</strong>${message ? `<span>${esc(message)}</span>` : ""}`;
    stack.appendChild(node);
    setTimeout(() => {
      node.style.opacity = "0";
      node.style.transform = "translateY(6px)";
      setTimeout(() => node.remove(), 220);
    }, 5200);
  }

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, options);
    if (response.status === 204) return null;
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (!response.ok) {
      const detail = payload?.detail;
      let code = `HTTP_${response.status}`;
      let message = `Request failed (${response.status}).`;
      if (typeof detail === "string") {
        message = detail;
      } else if (detail && typeof detail === "object") {
        code = detail.code || code;
        message = detail.message || message;
        if (Array.isArray(detail.errors) && detail.errors.length) {
          message = detail.errors.map((item) => item.msg || String(item)).join("; ");
        }
      }
      const error = new Error(message);
      error.code = code;
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  /* ------------------------------------------------------------------ */
  /* Boot                                                               */
  /* ------------------------------------------------------------------ */

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    applyTheme(localStorage.getItem("ledgerlens-theme") || "light");
    bindEvents();
    await Promise.allSettled([loadInfo(), loadCategories(), loadHistory()]);
    const hash = window.location.hash.match(/statement=([^&]+)/);
    if (hash) {
      await loadStatement(decodeURIComponent(hash[1]), { scroll: false });
    }
  }

  function bindEvents() {
    const dropzone = $("#dropzone");
    const fileInput = $("#file-input");
    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });
    fileInput.addEventListener("change", () => {
      if (fileInput.files?.length) handleFiles(Array.from(fileInput.files));
      fileInput.value = "";
    });
    ["dragenter", "dragover"].forEach((name) =>
      dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dropzone.classList.add("dragging");
      })
    );
    ["dragleave", "drop"].forEach((name) =>
      dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dropzone.classList.remove("dragging");
      })
    );
    dropzone.addEventListener("drop", (event) => {
      const files = Array.from(event.dataTransfer?.files || []);
      if (files.length) handleFiles(files);
    });

    $("#refresh-history").addEventListener("click", () => loadHistory(true));
    $("#merge-xlsx").addEventListener("click", () => mergeExport("xlsx"));
    $("#merge-csv").addEventListener("click", () => mergeExport("csv"));
    $("#export-xlsx").addEventListener("click", () => exportCurrent("xlsx"));
    $("#export-csv").addEventListener("click", () => exportCurrent("csv"));
    $("#retrain-btn").addEventListener("click", retrainModel);
    $("#theme-toggle").addEventListener("click", toggleTheme);
    $("#menu-toggle").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
    // Close sidebar on overlay click (mobile)
    const overlay = $("#sidebar-overlay");
    if (overlay) overlay.addEventListener("click", () => $("#sidebar").classList.remove("open"));

    $$(".nav-link").forEach((link) =>
      link.addEventListener("click", () => {
        $$(".nav-link").forEach((item) => item.classList.remove("active"));
        link.classList.add("active");
        $("#sidebar").classList.remove("open");
      })
    );

    $("#filter-search").addEventListener("input", debounce(() => {
      state.filters.search = $("#filter-search").value.trim();
      state.filters.page = 1;
      loadTransactions();
    }, 350));
    ["filter-date-from", "filter-date-to", "filter-category", "filter-type", "filter-sort"].forEach((id) => {
      $(`#${id}`).addEventListener("change", () => {
        state.filters.date_from = $("#filter-date-from").value;
        state.filters.date_to = $("#filter-date-to").value;
        state.filters.category = $("#filter-category").value;
        state.filters.type = $("#filter-type").value;
        state.filters.sort = $("#filter-sort").value;
        state.filters.page = 1;
        loadTransactions();
      });
    });
    $("#filter-flagged").addEventListener("change", () => {
      state.filters.flagged_only = $("#filter-flagged").checked;
      state.filters.page = 1;
      loadTransactions();
    });
    $("#clear-filters").addEventListener("click", clearFilters);
    $("#page-prev").addEventListener("click", () => {
      if (state.filters.page > 1) {
        state.filters.page -= 1;
        loadTransactions();
      }
    });
    $("#page-next").addEventListener("click", () => {
      if (state.transactions && state.filters.page < state.transactions.pages) {
        state.filters.page += 1;
        loadTransactions();
      }
    });

    $("#password-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const value = $("#password-input").value;
      if (!value) return;
      const resolve = state.passwordResolver;
      state.passwordResolver = null;
      hidePasswordModal();
      resolve?.(value);
    });
    $("#password-cancel").addEventListener("click", () => {
      const resolve = state.passwordResolver;
      state.passwordResolver = null;
      hidePasswordModal();
      resolve?.(null);
    });
    $("#password-modal").addEventListener("click", (event) => {
      if (event.target === $("#password-modal")) $("#password-cancel").click();
    });
  }

  /* ------------------------------------------------------------------ */
  /* System info / theme                                                */
  /* ------------------------------------------------------------------ */

  async function loadInfo() {
    try {
      const info = await api("/info");
      state.info = info;
      setStatus("api", true, "online");
      setStatus("ocr", Boolean(info.ocr_available), info.ocr_available ? "ready" : "off");
      setStatus("model", Boolean(info.model_available), info.model_available ? "ready" : "off");
    } catch (error) {
      setStatus("api", false, "offline");
      setStatus("ocr", false, "unknown");
      setStatus("model", false, "unknown");
    }
  }

  function setStatus(name, ok, label) {
    const dot = $(`#${name}-dot`);
    const text = $(`#${name}-status`);
    if (dot) {
      dot.classList.toggle("ok", Boolean(ok));
      dot.classList.toggle("bad", !ok);
    }
    if (text) text.textContent = label;
  }

  function applyTheme(theme) {
    const dark = theme === "dark";
    document.body.classList.toggle("dark", dark);
    const button = $("#theme-toggle");
    if (button) {
      const sunIcon = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`;
      const moonIcon = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
      button.innerHTML = dark
        ? `${sunIcon} Light mode`
        : `${moonIcon} Dark mode`;
    }
    localStorage.setItem("ledgerlens-theme", dark ? "dark" : "light");
  }

  function toggleTheme() {
    applyTheme(document.body.classList.contains("dark") ? "light" : "dark");
  }

  async function loadCategories() {
    try {
      state.categories = await api("/categories");
      const select = $("#filter-category");
      select.innerHTML = '<option value="">All categories</option>' + state.categories
        .map((item) => `<option value="${esc(item.name)}">${esc(item.name)}</option>`)
        .join("");
    } catch (error) {
      toast("Could not load categories", error.message, "error");
    }
  }

  async function retrainModel() {
    const button = $("#retrain-btn");
    const previous = button.textContent;
    button.disabled = true;
    button.textContent = "Training…";
    try {
      const result = await api("/classify/retrain", { method: "POST" });
      toast(
        "Classifier retrained",
        `${number(result.samples)} samples · accuracy ${pct(result.accuracy)} · ${number(result.overrides_used)} override(s) included.`
      );
      await loadInfo();
    } catch (error) {
      toast("Retraining failed", error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = previous;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Upload                                                             */
  /* ------------------------------------------------------------------ */

  async function handleFiles(files) {
    if (state.uploading) {
      toast("Upload already running", "Wait for the current batch to finish.", "warn");
      return;
    }
    const pdfs = files.filter((file) => file.name.toLowerCase().endsWith(".pdf"));
    if (!pdfs.length) {
      toast("No PDF selected", "Only .pdf files are supported.", "error");
      return;
    }
    const oversized = pdfs.filter((file) => file.size > MAX_FILE_MB * 1024 * 1024);
    if (oversized.length) {
      toast("File too large", `${oversized[0].name} is over ${MAX_FILE_MB} MB.`, "error");
      return;
    }

    state.uploading = true;
    $("#upload-count").textContent = `${pdfs.length} file${pdfs.length === 1 ? "" : "s"} queued`;
    $("#upload-progress").classList.remove("hidden");
    $("#progress-files").innerHTML = "";
    const rows = new Map();
    for (const file of pdfs) {
      const row = document.createElement("div");
      row.textContent = `○ ${file.name}`;
      $("#progress-files").appendChild(row);
      rows.set(file.name, row);
    }

    let lastStatement = null;
    let failures = 0;
    for (let index = 0; index < pdfs.length; index += 1) {
      const file = pdfs[index];
      const startPercent = Math.round((index / pdfs.length) * 100);
      setProgress(startPercent, `Processing ${index + 1} of ${pdfs.length}: ${file.name}`);
      rows.get(file.name).textContent = `… ${file.name}`;
      try {
        const statement = await uploadOne(file);
        rows.get(file.name).textContent = `✓ ${file.name} — ${number(statement.stats?.transaction_count)} transactions`;
        lastStatement = statement;
      } catch (error) {
        failures += 1;
        rows.get(file.name).textContent = `✕ ${file.name} — ${error.message}`;
        toast(`Could not process ${file.name}`, error.message, "error");
      }
      setProgress(Math.round(((index + 1) / pdfs.length) * 100), `Processed ${index + 1} of ${pdfs.length}`);
    }

    state.uploading = false;
    $("#upload-count").textContent = failures
      ? `${pdfs.length - failures} succeeded · ${failures} failed`
      : `${pdfs.length} processed`;
    await loadHistory();
    if (lastStatement) {
      await loadStatement(lastStatement.id, { scroll: true });
      toast(
        "Statement processed",
        `${lastStatement.filename}: ${number(lastStatement.stats?.transaction_count)} transactions, ${pct(lastStatement.extraction_confidence)} extraction confidence.`
      );
    }
    setTimeout(() => $("#upload-progress").classList.add("hidden"), 2600);
  }

  async function uploadOne(file) {
    let password = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const form = new FormData();
      form.append("file", file);
      if (password) form.append("password", password);
      try {
        return await api("/statements", { method: "POST", body: form });
      } catch (error) {
        if (error.code !== "NEEDS_PASSWORD") throw error;
        const prompt =
          attempt === 0
            ? "This PDF is encrypted. Enter the password to continue."
            : "That password did not work. Try again, or cancel to skip this file.";
        password = await askPassword(file.name, prompt);
        if (password === null) {
          const cancelled = new Error("Password prompt cancelled.");
          cancelled.code = "CANCELLED";
          throw cancelled;
        }
      }
    }
    throw new Error("Password was not accepted after 3 attempts.");
  }

  function setProgress(percent, label) {
    $("#progress-bar").style.width = `${Math.max(0, Math.min(100, percent))}%`;
    $("#progress-pct").textContent = `${percent}%`;
    $("#progress-label").textContent = label;
  }

  function askPassword(filename, message) {
    $("#password-message").textContent = `${filename} — ${message}`;
    $("#password-error").classList.add("hidden");
    $("#password-input").value = "";
    $("#password-modal").classList.remove("hidden");
    setTimeout(() => $("#password-input").focus(), 30);
    return new Promise((resolve) => {
      state.passwordResolver = resolve;
    });
  }

  function hidePasswordModal() {
    $("#password-modal").classList.add("hidden");
    $("#password-input").value = "";
  }

  /* ------------------------------------------------------------------ */
  /* History                                                            */
  /* ------------------------------------------------------------------ */

  async function loadHistory(notify = false) {
    try {
      state.history = await api("/statements?limit=100");
      const valid = new Set(state.history.map((item) => item.id));
      state.selectedIds = new Set([...state.selectedIds].filter((id) => valid.has(id)));
      renderHistory();
      if (notify) toast("History refreshed", `${state.history.length} statement(s) stored locally.`);
    } catch (error) {
      toast("Could not load history", error.message, "error");
    }
  }

  function renderHistory() {
    const list = $("#history-list");
    if (!state.history.length) {
      list.innerHTML = `<div class="empty-state"><strong>No statements yet</strong><span>Upload a PDF to build your local history.</span></div>`;
      updateMergeButtons();
      return;
    }
    list.innerHTML = state.history.map((item) => {
      const selected = state.selectedIds.has(item.id);
      const current = state.current?.id === item.id;
      const typeClass = String(item.pdf_type || "TEXT").toLowerCase();
      return `
        <div class="history-item ${current ? "current" : ""}" data-id="${esc(item.id)}">
          <input class="history-check" type="checkbox" data-select="${esc(item.id)}" ${selected ? "checked" : ""} aria-label="Select ${esc(item.filename)} for merge" />
          <div class="history-main" data-open="${esc(item.id)}" title="Open ${esc(item.filename)}">
            <strong>${esc(item.filename)}</strong>
            <span>${esc(item.bank_detected || "Unknown bank")} · ${formatDateTime(item.created_at)}</span>
          </div>
          <div class="history-metric"><strong>${number(item.transaction_count)}</strong>transactions</div>
          <div class="history-metric"><strong>${pct(item.extraction_confidence)}</strong>confidence</div>
          <div style="display:flex;align-items:center;gap:7px">
            <span class="badge ${typeClass}">${esc(item.pdf_type)}</span>
            <button class="history-delete" data-delete="${esc(item.id)}" type="button" title="Delete statement" aria-label="Delete ${esc(item.filename)}">✕</button>
          </div>
        </div>`;
    }).join("");

    $$("[data-select]", list).forEach((checkbox) =>
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.selectedIds.add(checkbox.dataset.select);
        else state.selectedIds.delete(checkbox.dataset.select);
        updateMergeButtons();
      })
    );
    $$("[data-open]", list).forEach((node) =>
      node.addEventListener("click", () => loadStatement(node.dataset.open, { scroll: true }))
    );
    $$("[data-delete]", list).forEach((button) =>
      button.addEventListener("click", () => deleteStatement(button.dataset.delete))
    );
    updateMergeButtons();
  }

  function updateMergeButtons() {
    const disabled = state.selectedIds.size === 0;
    $("#merge-xlsx").disabled = disabled;
    $("#merge-csv").disabled = disabled;
  }

  async function deleteStatement(id) {
    const item = state.history.find((entry) => entry.id === id);
    if (!item) return;
    if (!window.confirm(`Delete "${item.filename}" and its transactions from local storage?`)) return;
    try {
      await api(`/statements/${encodeURIComponent(id)}`, { method: "DELETE" });
      state.selectedIds.delete(id);
      if (state.current?.id === id) {
        state.current = null;
        state.transactions = null;
        state.summary = null;
        $("#statement-section").classList.add("hidden");
        $("#transactions-section").classList.add("hidden");
        $("#dashboard-section").classList.add("hidden");
        $("#current-statement-label").textContent = "No statement loaded";
        window.history.replaceState(null, "", window.location.pathname);
      }
      await loadHistory();
      toast("Statement deleted", item.filename);
    } catch (error) {
      toast("Could not delete statement", error.message, "error");
    }
  }

  /* ------------------------------------------------------------------ */
  /* Statement loading                                                  */
  /* ------------------------------------------------------------------ */

  async function loadStatement(id, { scroll = true } = {}) {
    showLoadingState();
    try {
      const [statement, summary] = await Promise.all([
        api(`/statements/${encodeURIComponent(id)}`),
        api(`/statements/${encodeURIComponent(id)}/summary`),
      ]);
      state.current = statement;
      state.summary = summary;
      state.filters = {
        page: 1, page_size: 50, date_from: "", date_to: "", category: "",
        type: "", search: "", flagged_only: false, sort: "date_asc",
      };
      syncFilterInputs();
      renderStatement(statement);
      renderDashboard(summary, statement);
      $("#statement-section").classList.remove("hidden");
      $("#transactions-section").classList.remove("hidden");
      $("#dashboard-section").classList.remove("hidden");
      $("#current-statement-label").textContent = statement.filename;
      window.history.replaceState(null, "", `#statement=${encodeURIComponent(id)}`);
      renderHistory();
      await loadTransactions();
      if (scroll) $("#statement-section").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      toast("Could not open statement", error.message, "error");
    }
  }

  function showLoadingState() {
    $("#statement-section").classList.remove("hidden");
    $("#transactions-section").classList.remove("hidden");
    $("#dashboard-section").classList.remove("hidden");
    $("#statement-title").textContent = "Loading statement…";
    $("#statement-subtitle").textContent = "Reconstructing the result view";
    $("#transactions-body").innerHTML = Array.from({ length: 5 }).map(() => `
      <tr>
        <td><div class="skeleton" style="width:70px"></div></td>
        <td><div class="skeleton" style="width:78%"></div></td>
        <td><div class="skeleton" style="width:62px;margin-left:auto"></div></td>
        <td><div class="skeleton" style="width:62px;margin-left:auto"></div></td>
        <td><div class="skeleton" style="width:70px;margin-left:auto"></div></td>
        <td><div class="skeleton" style="width:110px"></div></td>
        <td><div class="skeleton" style="width:58px"></div></td>
        <td><div class="skeleton" style="width:48px"></div></td>
      </tr>`).join("");
  }

  function renderStatement(statement) {
    const account = statement.account || {};
    const currency = account.currency || "INR";
    $("#statement-title").textContent = statement.filename;
    $("#statement-subtitle").textContent =
      `${statement.bank_detected || "Unknown bank"} · ${number(statement.num_pages)} page(s) · processed in ${number(statement.duration_ms)} ms`;
    $("#bank-avatar").textContent = (statement.bank_detected || account.account_holder_name || "B")
      .replace(/[^A-Za-z0-9]/g, "")
      .slice(0, 1)
      .toUpperCase() || "B";

    const type = String(statement.pdf_type || "TEXT").toLowerCase();
    const badge = $("#pdf-type-badge");
    badge.textContent = `${statement.pdf_type} PDF`;
    badge.className = `badge ${type}`;

    $("#account-holder").textContent = account.account_holder_name || "Not detected";
    $("#account-number").textContent = account.account_number_masked
      ? `A/c ${account.account_number_masked}`
      : account.account_number
        ? `A/c ${account.account_number}`
        : "Account number not detected";
    $("#account-bank").textContent = statement.bank_detected || "Unknown bank";
    $("#account-ifsc").textContent = account.ifsc ? `IFSC ${account.ifsc}` : "IFSC not detected";
    $("#account-period").textContent =
      account.statement_period_from && account.statement_period_to
        ? `${formatDate(account.statement_period_from)} → ${formatDate(account.statement_period_to)}`
        : "Period not detected";
    $("#account-branch").textContent = account.branch || account.customer_id
      ? [account.branch, account.customer_id ? `CIF ${account.customer_id}` : ""].filter(Boolean).join(" · ")
      : "Branch not detected";
    $("#account-balances").textContent =
      `${money(account.opening_balance, currency)} → ${money(account.closing_balance, currency)}`;
    $("#account-reconciled").textContent = statement.stats?.closing_reconciled
      ? "Reconciled to closing balance"
      : "Not reconciled";

    const confidence = Number(statement.extraction_confidence || 0);
    $("#confidence-value").textContent = pct(confidence);
    $("#confidence-bar").style.width = `${Math.max(0, Math.min(100, confidence * 100))}%`;
    $("#confidence-sub").textContent =
      `${pct(statement.stats?.reconciled_ratio || 0)} rows reconciled · ${number(statement.stats?.flagged_count)} flagged`;

    const warnings = Array.isArray(statement.warnings) ? statement.warnings : [];
    $("#warnings-count").textContent = number(warnings.length);
    const block = $("#warnings-block");
    block.classList.toggle("has-warnings", warnings.length > 0);
    $("#warnings-list").innerHTML = warnings.length
      ? warnings.map((warning) => `<li>${esc(humanizeWarning(warning))}</li>`).join("")
      : "<li>No warnings. Required fields were found and balances reconcile.</li>";
  }

  function humanizeWarning(warning) {
    return String(warning)
      .replace(/_/g, " ")
      .replace(/^./, (character) => character.toUpperCase());
  }

  /* ------------------------------------------------------------------ */
  /* Transactions                                                       */
  /* ------------------------------------------------------------------ */

  function syncFilterInputs() {
    $("#filter-search").value = "";
    $("#filter-date-from").value = "";
    $("#filter-date-to").value = "";
    $("#filter-category").value = "";
    $("#filter-type").value = "";
    $("#filter-sort").value = "date_asc";
    $("#filter-flagged").checked = false;
  }

  function clearFilters() {
    state.filters = {
      page: 1, page_size: 50, date_from: "", date_to: "", category: "",
      type: "", search: "", flagged_only: false, sort: "date_asc",
    };
    syncFilterInputs();
    loadTransactions();
  }

  function buildFilterQuery(includePage = true) {
    const params = new URLSearchParams();
    if (includePage) {
      params.set("page", String(state.filters.page));
      params.set("page_size", String(state.filters.page_size));
    }
    if (state.filters.date_from) params.set("date_from", state.filters.date_from);
    if (state.filters.date_to) params.set("date_to", state.filters.date_to);
    if (state.filters.category) params.set("category", state.filters.category);
    if (state.filters.type) params.set("type", state.filters.type);
    if (state.filters.search) params.set("search", state.filters.search);
    if (state.filters.flagged_only) params.set("flagged_only", "true");
    params.set("sort", state.filters.sort);
    return params.toString();
  }

  async function loadTransactions() {
    if (!state.current) return;
    try {
      const query = buildFilterQuery(true);
      const data = await api(`/statements/${encodeURIComponent(state.current.id)}/transactions?${query}`);
      state.transactions = data;
      renderTransactions(data);
    } catch (error) {
      toast("Could not load transactions", error.message, "error");
    }
  }

  function visibleFlags(flags) {
    return (flags || []).filter(
      (flag) => !String(flag).startsWith("row:") && !String(flag).startsWith("value_date:")
    );
  }

  function renderTransactions(data) {
    const body = $("#transactions-body");
    $("#txn-count-pill").textContent = `${number(data.total)} row${data.total === 1 ? "" : "s"}`;
    $("#transactions-subtitle").textContent =
      `Showing ${number(data.items.length)} of ${number(data.total)} transactions · page totals: ${money(data.total_debit)} debit / ${money(data.total_credit)} credit`;
    $("#page-info").textContent = `Page ${data.page} of ${Math.max(1, data.pages)}`;
    $("#page-prev").disabled = data.page <= 1;
    $("#page-next").disabled = data.page >= data.pages;
    $("#page-total").textContent = `${number(data.total)} matching rows`;

    if (!data.items.length) {
      body.innerHTML = `<tr><td colspan="8"><div class="empty-state"><strong>No matching transactions</strong><span>Try clearing filters or broadening the date range.</span></div></td></tr>`;
      return;
    }

    body.innerHTML = data.items.map((txn) => {
      const flags = visibleFlags(txn.flags);
      const isFlagged = flags.length > 0 || txn.category_source === "fallback";
      const rowClass = [isFlagged ? "flagged" : "", txn.recurring ? "recurring" : ""].filter(Boolean).join(" ");
      const source = String(txn.category_source || "fallback");
      const categoryOptions = state.categories
        .map((item) => `<option value="${esc(item.name)}" ${item.name === txn.category ? "selected" : ""}>${esc(item.name)}</option>`)
        .join("");
      const meta = [
        txn.reference_no ? `<code>${esc(txn.reference_no)}</code>` : "",
        `<span>page ${number(txn.page)}</span>`,
        txn.recurring ? '<span class="flag-chip neutral">recurring</span>' : "",
        txn.value_date ? `<span>value ${esc(formatDate(txn.value_date))}</span>` : "",
      ].filter(Boolean).join(" · ");

      return `
        <tr class="${rowClass}" data-txn="${txn.id}">
          <td class="col-date">${esc(formatDate(txn.date))}</td>
          <td class="txn-desc">
            <strong title="${esc(txn.raw_description || txn.description)}">${esc(txn.description)}</strong>
            <div class="txn-meta">${meta}</div>
          </td>
          <td class="num debit">${txn.debit !== null ? money(txn.debit) : "—"}</td>
          <td class="num credit">${txn.credit !== null ? money(txn.credit) : "—"}</td>
          <td class="num">${txn.balance !== null ? money(txn.balance) : "—"}</td>
          <td class="col-category">
            <select class="category-select" data-id="${txn.id}" data-previous="${esc(txn.category)}" aria-label="Category for ${esc(txn.description.slice(0, 50))}">
              ${categoryOptions}
            </select>
            <span class="confidence-mini">${pct(txn.category_confidence)} confidence</span>
          </td>
          <td class="col-source">
            <span class="source-chip ${esc(source)}">${esc(source)}</span>
            <span class="confidence-mini" title="${esc(txn.reason || "")}">${esc((txn.reason || "").slice(0, 54))}</span>
          </td>
          <td>
            ${flags.length
              ? flags.map((flag) => `<span class="flag-chip">${esc(String(flag).replaceAll("_", " "))}</span>`).join("")
              : '<span class="muted">—</span>'}
          </td>
        </tr>`;
    }).join("");

    $$(".category-select", body).forEach((select) =>
      select.addEventListener("change", () => updateCategory(select))
    );
  }

  async function updateCategory(select) {
    const id = select.dataset.id;
    const previous = select.dataset.previous;
    const category = select.value;
    if (category === previous) return;
    select.disabled = true;
    select.classList.add("saving");
    try {
      const result = await api(`/transactions/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, apply_to_similar: true }),
      });
      select.dataset.previous = category;
      toast(
        "Category updated",
        result.updated_count > 1
          ? `${number(result.updated_count)} similar transactions updated; override saved for future runs.`
          : "Override saved for future runs."
      );
      await Promise.all([loadTransactions(), loadSummaryAndDashboard()]);
    } catch (error) {
      select.value = previous;
      toast("Could not update category", error.message, "error");
    } finally {
      select.disabled = false;
      select.classList.remove("saving");
    }
  }

  /* ------------------------------------------------------------------ */
  /* Summary / dashboard                                                */
  /* ------------------------------------------------------------------ */

  async function loadSummaryAndDashboard() {
    if (!state.current) return;
    try {
      const summary = await api(`/statements/${encodeURIComponent(state.current.id)}/summary`);
      state.summary = summary;
      renderDashboard(summary, state.current);
    } catch (error) {
      toast("Could not refresh summary", error.message, "error");
    }
  }

  function renderDashboard(summary, statement) {
    const currency = statement?.account?.currency || "INR";
    $("#kpi-credit").textContent = money(summary.total_credit, currency);
    $("#kpi-debit").textContent = money(summary.total_debit, currency);
    $("#kpi-net").textContent = money(summary.net, currency);
    $("#kpi-net-sub").textContent = summary.net >= 0 ? "Net inflow" : "Net outflow";
    $("#kpi-credit-count").textContent = `${number(summary.category_breakdown.length)} categories`;
    $("#kpi-debit-count").textContent = `${number(summary.transaction_count)} transactions`;
    const reconciled = Number(statement?.stats?.reconciled_ratio || 0);
    $("#kpi-recon").textContent = pct(reconciled);
    $("#kpi-recon-sub").textContent =
      `${number(statement?.stats?.reconciled_rows || 0)}/${number(statement?.stats?.transaction_count || 0)} rows reconcile`;
    $("#dashboard-pill").textContent =
      `${number(summary.transaction_count)} transactions · ${number(summary.monthly.length)} month(s)`;

    renderCategoryChart(summary, currency);
    renderMonthlyChart(summary, currency);
    renderBalanceChart(summary, currency);
    renderMerchantChart(summary, currency);
  }

  function renderCategoryChart(summary, currency) {
    const container = $("#category-chart");
    let items = (summary.category_breakdown || []).filter((item) => Number(item.debit) > 0);
    if (!items.length) {
      items = (summary.category_breakdown || []).filter((item) => Number(item.credit) > 0);
    }
    if (!items.length) {
      container.innerHTML = '<div class="chart-empty">No category data available.</div>';
      return;
    }
    items = [...items].sort((a, b) => Number(b.debit || b.credit) - Number(a.debit || a.credit));
    if (items.length > 8) {
      const rest = items.slice(8);
      const other = rest.reduce(
        (acc, item) => {
          acc.count += item.count;
          acc.debit += Number(item.debit);
          acc.credit += Number(item.credit);
          return acc;
        },
        { category: "Other", count: 0, debit: 0, credit: 0 }
      );
      items = items.slice(0, 8).concat(other);
    }
    const total = items.reduce((sum, item) => sum + (Number(item.debit) || Number(item.credit)), 0) || 1;
    const radius = 54;
    const circumference = 2 * Math.PI * radius;
    let offset = 0;
    const segments = items.map((item, index) => {
      const value = Number(item.debit) || Number(item.credit);
      const length = (value / total) * circumference;
      const segment = `
        <circle cx="85" cy="85" r="${radius}" fill="none" stroke="${COLORS[index % COLORS.length]}"
          stroke-width="20" stroke-dasharray="${length} ${circumference - length}"
          stroke-dashoffset="${-offset}" transform="rotate(-90 85 85)">
          <title>${esc(item.category)}: ${money(value, currency)}</title>
        </circle>`;
      offset += length;
      return segment;
    }).join("");

    const legend = items.map((item, index) => {
      const value = Number(item.debit) || Number(item.credit);
      return `
        <div class="legend-item">
          <span class="legend-swatch" style="background:${COLORS[index % COLORS.length]}"></span>
          <span>${esc(item.category)} <strong>${money(value, currency)}</strong> · ${pct(value / total)}</span>
        </div>`;
    }).join("");

    container.innerHTML = `
      <div class="donut-wrap">
        <svg class="donut-svg" viewBox="0 0 170 170" role="img" aria-label="Spend by category donut chart">
          ${segments}
          <text x="85" y="80" class="donut-total">${esc(compactMoney(total))}</text>
          <text x="85" y="97" class="donut-center">total debit</text>
        </svg>
        <div class="legend" style="flex:1;min-width:210px">${legend}</div>
      </div>`;
  }

  function renderMonthlyChart(summary, currency) {
    const container = $("#monthly-chart");
    const months = summary.monthly || [];
    if (!months.length) {
      container.innerHTML = '<div class="chart-empty">No monthly data available.</div>';
      return;
    }
    const width = 640;
    const height = 265;
    const left = 56;
    const right = 16;
    const top = 18;
    const bottom = 42;
    const plotW = width - left - right;
    const plotH = height - top - bottom;
    const maxValue = Math.max(1, ...months.flatMap((item) => [Number(item.credit), Number(item.debit)]));
    const groupW = plotW / months.length;
    const barW = Math.max(5, Math.min(18, groupW * 0.27));
    const grid = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
      const y = top + plotH - ratio * plotH;
      return `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="var(--line)" stroke-width="1" stroke-dasharray="3 5"/>
        <text x="${left - 8}" y="${y + 3}" text-anchor="end" font-size="8" fill="var(--muted)">${esc(compactMoney(maxValue * ratio))}</text>`;
    }).join("");
    const bars = months.map((item, index) => {
      const x = left + groupW * index + groupW / 2;
      const credit = Number(item.credit || 0);
      const debit = Number(item.debit || 0);
      const creditH = (credit / maxValue) * plotH;
      const debitH = (debit / maxValue) * plotH;
      const label = new Date(`${item.month}-01T00:00:00`).toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
      return `
        <g>
          <rect x="${x - barW - 2}" y="${top + plotH - creditH}" width="${barW}" height="${creditH}" rx="3" fill="#0f5c6b">
            <title>${esc(label)} credit: ${money(credit, currency)}</title>
          </rect>
          <rect x="${x + 2}" y="${top + plotH - debitH}" width="${barW}" height="${debitH}" rx="3" fill="#d97706">
            <title>${esc(label)} debit: ${money(debit, currency)}</title>
          </rect>
          <text x="${x}" y="${height - 22}" text-anchor="middle" font-size="8" fill="var(--muted)">${esc(label)}</text>
        </g>`;
    }).join("");
    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Monthly credit and debit bar chart">
        ${grid}
        ${bars}
        <line x1="${left}" y1="${top + plotH}" x2="${width - right}" y2="${top + plotH}" stroke="var(--line-strong)"/>
        <g transform="translate(${left}, ${height - 6})">
          <rect x="0" y="-7" width="8" height="8" rx="2" fill="#0f5c6b"/><text x="13" y="0" font-size="8" fill="var(--muted)">Credit</text>
          <rect x="70" y="-7" width="8" height="8" rx="2" fill="#d97706"/><text x="83" y="0" font-size="8" fill="var(--muted)">Debit</text>
        </g>
      </svg>`;
  }

  function renderBalanceChart(summary, currency) {
    const container = $("#balance-chart");
    const series = summary.balance_series || [];
    if (!series.length) {
      container.innerHTML = '<div class="chart-empty">No running balance data available.</div>';
      return;
    }
    const width = 900;
    const height = 265;
    const left = 64;
    const right = 22;
    const top = 18;
    const bottom = 40;
    const plotW = width - left - right;
    const plotH = height - top - bottom;
    const values = series.map((item) => Number(item.balance));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const pad = Math.max(1, (max - min) * 0.12);
    const low = min - pad;
    const high = max + pad;
    const x = (index) => left + (series.length === 1 ? plotW / 2 : (index / (series.length - 1)) * plotW);
    const y = (value) => top + plotH - ((value - low) / (high - low || 1)) * plotH;
    const points = series.map((item, index) => `${x(index).toFixed(1)},${y(Number(item.balance)).toFixed(1)}`).join(" ");
    const area = `${left},${top + plotH} ${points} ${left + plotW},${top + plotH}`;
    const dots = series.length <= 60
      ? series.map((item, index) => `
          <circle cx="${x(index).toFixed(1)}" cy="${y(Number(item.balance)).toFixed(1)}" r="3.2" fill="var(--surface)" stroke="#0f5c6b" stroke-width="2">
            <title>${esc(formatDate(item.date))} · ${money(item.balance, currency)} · ${esc(item.description || "")}</title>
          </circle>`).join("")
      : "";
    const grid = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
      const value = low + (high - low) * ratio;
      const yy = y(value);
      return `<line x1="${left}" y1="${yy}" x2="${width - right}" y2="${yy}" stroke="var(--line)" stroke-width="1" stroke-dasharray="3 5"/>
        <text x="${left - 9}" y="${yy + 3}" text-anchor="end" font-size="8" fill="var(--muted)">${esc(compactMoney(value))}</text>`;
    }).join("");
    const ticks = [0, Math.floor(series.length / 2), series.length - 1]
      .filter((value, index, array) => array.indexOf(value) === index)
      .map((index) => `<text x="${x(index)}" y="${height - 18}" text-anchor="middle" font-size="8" fill="var(--muted)">${esc(formatShortDate(series[index].date))}</text>`)
      .join("");
    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Running balance line chart">
        <defs>
          <linearGradient id="balance-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#0f5c6b" stop-opacity="0.24"/>
            <stop offset="100%" stop-color="#0f5c6b" stop-opacity="0.01"/>
          </linearGradient>
        </defs>
        ${grid}
        <polygon points="${area}" fill="url(#balance-fill)"/>
        <polyline points="${points}" fill="none" stroke="#0f5c6b" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>
        ${dots}
        ${ticks}
      </svg>`;
  }

  function renderMerchantChart(summary, currency) {
    const container = $("#merchant-chart");
    const merchants = (summary.top_merchants || []).slice(0, 6);
    if (!merchants.length) {
      container.innerHTML = '<div class="chart-empty">No merchant data available.</div>';
      return;
    }
    const max = Math.max(1, ...merchants.map((item) => Number(item.amount)));
    container.innerHTML = `<div class="merchant-list">${merchants.map((item) => `
      <div class="merchant-row">
        <span class="merchant-name" title="${esc(item.merchant)}">${esc(item.merchant)} <span class="muted">· ${number(item.count)}×</span></span>
        <span class="merchant-amount">${money(item.amount, currency)}</span>
        <div class="merchant-track"><div class="merchant-bar" style="width:${Math.max(3, (Number(item.amount) / max) * 100)}%"></div></div>
      </div>`).join("")}</div>`;
  }

  /* ------------------------------------------------------------------ */
  /* Exports                                                            */
  /* ------------------------------------------------------------------ */

  function triggerDownload(url) {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  }

  function exportCurrent(format) {
    if (!state.current) {
      toast("No statement loaded", "Upload a PDF first.", "warn");
      return;
    }
    const query = buildFilterQuery(false);
    triggerDownload(`/api/statements/${encodeURIComponent(state.current.id)}/export?format=${format}&${query}`);
    toast(`Preparing ${format.toUpperCase()}`, "The download starts in a moment.");
  }

  function mergeExport(format) {
    if (!state.selectedIds.size) {
      toast("Nothing selected", "Tick statements in the history list to merge.", "warn");
      return;
    }
    const ids = [...state.selectedIds].map(encodeURIComponent).join(",");
    triggerDownload(`/api/merge/export?ids=${ids}&format=${format}`);
    toast(`Merging ${state.selectedIds.size} statement(s)`, `Preparing a combined ${format.toUpperCase()} export.`);
  }
})();
