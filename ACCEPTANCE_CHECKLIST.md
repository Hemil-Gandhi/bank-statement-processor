# Acceptance Checklist

Status against `BUILD_SPEC.md` §8 and the Phase 11–12 requirements.
Legend: **DONE** = implemented and verified on this machine; **PARTIAL** =
implemented/documented but not fully verifiable here.

Verified environment: Windows, Python 3.14 venv, Tesseract 5.5.0, SQLite.
Test suite: **66 passed** (`pytest -q`). Classifier: accuracy **0.9971**,
macro F1 **0.9972** on 348 held-out samples.

## Core acceptance checklist

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Upload a text-based PDF → correct transactions, account details, categories | **DONE** | SBI 36/36 rows, HDFC 16, ICICI 12, Axis 10, generic 8; all 100% reconciled; API test `test_upload_results_summary_edit_and_export` |
| 2 | Upload a scanned/image PDF → OCR path auto-selected, transactions extracted | **DONE** | `scanned_statement.pdf` detected `IMAGE`, 8/8 rows, closing reconciled; `test_scanned_pdf_uses_ocr_and_reconciles` |
| 3 | Mixed PDF handled page by page | **DONE** | `mixed_statement.pdf` → `per_page_types=["TEXT","IMAGE"]`, 36/36 rows; `test_mixed_pdf_uses_per_page_detection` |
| 4 | ≥3 different bank layouts + generic fallback work | **DONE** | SBI, HDFC, ICICI (Dr/Cr marker), Axis (signed amount) + generic borderless; all reconcile |
| 5 | Debit/Credit/Balance correctly separated; balances reconcile on fixtures | **DONE** | 100% row reconciliation and closing reconciliation on all fixtures; validator repair tests |
| 6 | Classification uses only rules + classical ML (no LLM/API calls) and shows source/confidence | **DONE** | YAML rules + TF-IDF/Logistic Regression; `category_source`, `category_confidence`, `reason` persisted and shown; no outbound AI calls |
| 7 | Users can edit categories; overrides persist and are applied next time | **DONE** | `PATCH /api/transactions/{id}` stores `user_overrides`; classifier checks overrides first; API test asserts override persistence |
| 8 | Export to .xlsx (multi-sheet, charts) and .csv works and opens cleanly in Excel | **DONE** | Account Details / Transactions / Category Summary / Monthly Summary with charts; CSV UTF-8 BOM; openpyxl tests; samples in `samples/exports/` |
| 9 | Frontend: upload, results, filters, dashboard, export all functional | **DONE** | Static SPA served at `/`; drag-drop multi-file, password modal, history, filters/search/pagination, inline edit, SVG dashboard, exports, merge, dark mode |
| 10 | Tests pass (`pytest`), classifier metrics report generated | **DONE** | `66 passed`; `docs/classifier_metrics.md`, `docs/confusion_matrix.csv/.svg` |
| 11 | Docker one-command run works; README complete | **PARTIAL** | `Dockerfile`, `docker-compose.yml`, `.dockerignore` authored; README complete. **Not executed** because Docker is not installed on this machine (`docker --version` → command not found). |

## Phase 11 advanced features

| Feature | Status | Notes |
|---|---|---|
| Auto text/image detection per page (mixed PDFs) | **DONE** | PyMuPDF text-quality + image-coverage heuristics, garbage-layer detection |
| Password-protected PDFs | **DONE** | Empty/wrong password → `NEEDS_PASSWORD`; retry with `demo123` works |
| Multi-page and multi-statement-per-file handling | **DONE** | Whole file combined; multiple account/period warnings; merged exports |
| Multi-bank profiles + generic fallback | **DONE** | 7 dedicated profiles + generic; data-driven `BankProfile` |
| Multi-line narration merging | **DONE** | Continuation lines append to previous transaction; fixture exercises page-break continuation |
| Repeated headers/footers removal | **DONE** | Summary/footer patterns + header re-detection per page |
| Balance reconciliation + auto-repair + confidence score | **DONE** | Swap/spurious-column/OCR-digit repair; weighted confidence |
| Duplicate-transaction detection across page boundaries | **DONE** | Date+description+amount+balance key; `duplicates_removed` |
| Single-column amount with Dr/Cr marker | **DONE** | ICICI fixture (`single_marker`), parentheses/sign support |
| OCR preprocessing + OCR digit-fix heuristics | **DONE** | Grayscale, denoise, adaptive threshold, deskew, border removal; digit repair against balance delta |
| UPI payee/merchant parsing | **DONE** | VPA, payee, reference, remark extraction; merchant key for recurring |
| User-correctable categories with learning loop | **DONE** | Override memory + `apply_to_similar` + retrain endpoint/CLI |
| Explainable classification | **DONE** | `source`, `confidence`, `reason` on every row |
| Recurring-transaction detection | **DONE** | Same merchant+amount across ≥2 months or ≥3 hits; month tokens stripped from merchant key |
| Merging multiple statements into one export | **DONE** | `/api/merge/export` + history selection in UI |
| Filters, search, summary dashboard | **DONE** | API filters and SVG dashboard |
| Logging, structured errors, YAML rules, tests, Docker | **PARTIAL** | All implemented; Docker not executable on this machine |

## Phase 12 testing and quality

| Requirement | Status | Notes |
|---|---|---|
| Sample generator with ≥3 bank-like layouts, Dr/Cr variants, date formats, image/rotation/noise | **DONE** | `scripts/generate_sample_pdfs.py`; 5 text layouts + scanned + mixed + encrypted + empty |
| Unit tests: date, amount, IFSC/account, bank detector, header, row merge, validator, rules, UPI, ML smoke, exporters | **DONE** | 66 tests across 7 files |
| Integration tests: upload fixtures, assert counts/totals/reconciliation | **DONE** | API + pipeline tests cover text, scanned, mixed, password, empty, merge |
| Classifier report ≥ 90% accuracy/F1 | **DONE** | 0.9971 accuracy / 0.9972 macro F1 |
| Edge-case checklist has a test or documented behaviour | **DONE** | See README “Edge-case behaviour”; tests cover empty/corrupt/non-PDF, password right/wrong, skewed scan, missing amount/balance, swap repair, reverse order, multi-line, duplicates |
| Huge file | **DONE (guard) / documented** | `BSP_MAX_FILE_SIZE_MB` → `413 FILE_TOO_LARGE`; not exercised with a 25 MB fixture |
| Concurrent uploads | **DOCUMENTED** | Sync FastAPI + SQLite WAL; no dedicated concurrency stress test |
| Very faint text / low-DPI | **DOCUMENTED** | OCR confidence recorded; low-confidence words dropped and warning emitted |

## Phase 13 documentation and delivery

| Requirement | Status | Notes |
|---|---|---|
| README: overview, architecture, setup, config, usage, API, bank profile, rules, retrain, limitations, future | **DONE** | `README.md` |
| Sample input PDFs + sample exported XLSX/CSV in `/samples` | **DONE** | 9 fixture PDFs; `samples/exports/` contains SBI, HDFC and merged XLSX/CSV |
| Demo script | **DONE** | Step-by-step walkthrough in README |

## Honest gaps

1. **Docker was not run** on this machine. Files follow a standard
   `python:3.12-slim` + Tesseract + Poppler setup and should be verified with
   `docker compose up --build` on a machine with Docker.
2. A real 25 MB upload and a true concurrent-upload stress test were not
   executed; both are guarded/documented rather than load-tested.
3. Real bank statements vary widely; the generic fallback and override loop are
   the intended mitigation for layouts not covered by a profile.
