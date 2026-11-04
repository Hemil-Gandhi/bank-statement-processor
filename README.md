<p align="center">
  <img src="https://img.shields.io/badge/LedgerLens-Bank%20Statement%20Processor-0a7a8a?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCA2NCI+PHJlY3Qgd2lkdGg9IjY0IiBoZWlnaHQ9IjY0IiByeD0iMTQiIGZpbGw9IiMwYTdhOGEiLz48cGF0aCBkPSJNMTggNDRWMjBoOGw2IDEyIDYtMTJoOHYyNGgtN1YzMWwtNyAxMy03LTEzdjEzeiIgZmlsbD0iI2ZmZiIvPjwvc3ZnPg==" alt="LedgerLens" />
  <br/>
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Tests-66%20passed-brightgreen?style=flat-square&logo=pytest&logoColor=white" />
  <img src="https://img.shields.io/badge/Accuracy-99.71%25-success?style=flat-square" />
  <img src="https://img.shields.io/badge/No%20LLM-100%25%20Local-blueviolet?style=flat-square" />
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white" />
</p>

<h1 align="center">LedgerLens — Bank Statement Processor</h1>

<p align="center">
  A <strong>fully local, full-stack</strong> application that turns Indian bank statement PDFs into a clean, categorised transaction ledger.<br/>
  Handles text, scanned (OCR), mixed and password-protected PDFs.<br/>
  <strong>No LLM. No external AI. No cloud calls. Every byte stays on your machine.</strong>
</p>

---

## ✨ What it does

| Feature | Details |
|---|---|
| 📄 **PDF types** | TEXT, IMAGE (scanned), MIXED — detected per page |
| 🔍 **Text extraction** | pdfplumber word boxes + ruling-line hints, PyMuPDF fallback |
| 🖼️ **OCR pipeline** | PyMuPDF @ 300 DPI → OpenCV deskew/denoise/threshold → Tesseract |
| 📊 **Table reconstruction** | Header detection, column boundaries, multi-line narration, borderless fallback |
| 🏦 **Account details** | Holder name, account number (masked), IFSC, branch, MICR, statement period, opening/closing balance |
| ⚖️ **Balance reconciliation** | `prev + credit − debit == balance` with 0.01 tolerance, auto-repair for swapped Dr/Cr and OCR errors |
| 🏷️ **Classification** | 29-category taxonomy — YAML rule engine → TF-IDF + Logistic Regression fallback |
| 🧠 **Learning loop** | Inline edits persist as overrides, `Retrain model` refits instantly |
| 🔄 **Recurring detection** | Same merchant + amount across months tagged `recurring` |
| 📤 **Exports** | Multi-sheet Excel (with charts) and UTF-8-BOM CSV; multi-statement merge |
| 🌙 **Dark mode** | Full dark/light theme toggle with localStorage persistence |
| 🗄️ **Persistence** | SQLite via SQLAlchemy; uploaded PDFs deleted after processing by default |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser SPA  (vanilla HTML / CSS / JS, served by FastAPI at /)  │
│  Upload · History · Statement · Transactions · Dashboard         │
└───────────────────────────────┬──────────────────────────────────┘
                                │  JSON / multipart
┌───────────────────────────────▼──────────────────────────────────┐
│  FastAPI  (backend/app/main.py)                                  │
│  /api/statements  /api/transactions  /api/summary  /api/export   │
└───────────────────────────────┬──────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────┐
│  Pipeline  (core/pipeline.py)                                    │
│                                                                  │
│  PDF detector → word-box layer → bank detector → account parser  │
│       │                │                                         │
│       │          TEXT: pdfplumber                                │
│       │          IMAGE: OpenCV + Tesseract                       │
│       ▼                ▼                                         │
│  table reconstructor → normalizer → classifier → SQLite persist  │
│                        (reconcile)   (rules → ML)                │
└───────────────────────────────┬──────────────────────────────────┘
                                │
              ┌─────────────────┼──────────────┐
              ▼                 ▼              ▼
        SQLite (jobs,      XLSX / CSV      docs/ metrics
        transactions,      exporters       + confusion matrix
        overrides)
```

Money is stored as `Decimal` in domain/database layers, exposed as `float` only at the JSON boundary.

---

## 🚀 Quick Start (Local)

### Prerequisites

- **Python 3.12+** (developed on Python 3.14)
- **Tesseract OCR 5.x** — required only for scanned PDFs
  - **Windows:** [UB Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) (auto-detected at `C:\Program Files\Tesseract-OCR\tesseract.exe`)
  - **Linux:** `sudo apt-get install tesseract-ocr tesseract-ocr-eng`
  - **macOS:** `brew install tesseract`
- No Node.js required — the frontend is static HTML/CSS/JS, served by FastAPI

### Setup & Run

**Windows (PowerShell)**

```powershell
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/bank-statement-processor.git
cd bank-statement-processor

# 2. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r backend\requirements.txt

# 4. Start the server
cd backend
$env:PYTHONPATH = (Get-Location).Path
..\\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Linux / macOS**

```bash
git clone https://github.com/YOUR_USERNAME/bank-statement-processor.git
cd bank-statement-processor

python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cd backend
PYTHONPATH="$PWD" ../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** in your browser.

- 📖 Interactive API docs: **http://localhost:8000/api/docs**
- ❤️ Health check: **http://localhost:8000/api/health**

---

## 🐳 Quick Start (Docker)

```bash
git clone https://github.com/YOUR_USERNAME/bank-statement-processor.git
cd bank-statement-processor
docker compose up --build
```

Open **http://localhost:8000**. The image includes Tesseract (English + Hindi), Poppler and OpenCV. SQLite data lives in the `bsp_data` volume.

```bash
docker compose logs -f      # Follow logs
docker compose down         # Stop
docker compose down -v      # Stop + remove database volume
```

---

## 🗺️ Demo Walkthrough

1. Open `http://localhost:8000`
2. Drag `samples/sbi_statement.pdf` onto the upload zone
3. Review the **Statement** card — bank, holder name, PDF type, confidence meter, reconciliation stats, warnings
4. In **Transactions**, filter by `Debit`, search `salary`, or change a category inline — the correction is saved immediately as an override
5. Open **Dashboard** — category donut, monthly cash flow bars, top merchants, running balance chart
6. Click **Export XLSX** or **Export CSV** to download the filtered rows
7. Upload `samples/scanned_statement.pdf` to exercise the OCR path
8. Upload `samples/password_protected.pdf` — UI prompts for password `demo123`
9. Select two statements in **History** → **Merge XLSX** / **Merge CSV**
10. Click **Retrain model** to append stored overrides and refit the classifier

---

## 📂 Sample Fixtures

Generated by `scripts/generate_sample_pdfs.py` with ReportLab + PyMuPDF.

| File | Description | Pages | Transactions | Reconciled |
|---|---|---:|---:|:---:|
| `sbi_statement.pdf` | SBI · separate Dr/Cr · multi-line narration | 2 | 36 | ✅ 100% |
| `hdfc_statement.pdf` | HDFC · separate Dr/Cr | 1 | 16 | ✅ 100% |
| `icici_statement.pdf` | ICICI · single amount + Dr/Cr marker | 1 | 12 | ✅ 100% |
| `axis_statement.pdf` | Axis · signed amount | 1 | 10 | ✅ 100% |
| `generic_statement.pdf` | Borderless generic fallback | 1 | 8 | ✅ 100% |
| `scanned_statement.pdf` | Image-only · rotated + noise | 1 | 8 | ✅ 100% |
| `mixed_statement.pdf` | Page 1 text + page 2 image | 2 | 36 | ✅ 100% |
| `password_protected.pdf` | AES-256 · password `demo123` | 2 | 36 | ✅ 100% |
| `empty.pdf` | Blank page | 1 | 0 | — |

Regenerate fixtures:
```bash
# Windows
.venv\Scripts\python scripts\generate_sample_pdfs.py --out samples
# Linux/macOS
.venv/bin/python scripts/generate_sample_pdfs.py --out samples
```

---

## ⚙️ Configuration

All settings use `BSP_*` environment variables with sensible defaults.

| Variable | Default | Purpose |
|---|---|---|
| `BSP_DATA_DIR` | `backend/data` | SQLite DB, upload scratch, model/training |
| `BSP_DATABASE_URL` | `sqlite:///<data>/app.db` | SQLAlchemy connection URL |
| `BSP_MODEL_PATH` | `<data>/models/classifier.joblib` | Trained classifier binary |
| `BSP_TRAINING_CSV` | `<data>/training/transactions_labeled.csv` | Training corpus |
| `BSP_FRONTEND_DIR` | `frontend/` | Static SPA directory |
| `BSP_MAX_FILE_SIZE_MB` | `25` | Upload size limit (MB) |
| `BSP_MAX_PAGES` | `100` | Page-count limit |
| `BSP_OCR_DPI` | `300` | OCR render DPI |
| `BSP_OCR_MIN_CONF` | `30` | Drop OCR words below this confidence |
| `BSP_OCR_LANG` | `eng` | Tesseract language(s), e.g. `eng+hin` |
| `BSP_KEEP_UPLOADS` | `0` | Set `1` to keep uploaded PDFs |
| `BSP_LOG_LEVEL` | `INFO` | Logging level |
| `TESSERACT_CMD` | auto-detected | Explicit path to Tesseract binary |

---

## 🌐 API Reference

**Base URL:** `http://localhost:8000/api`

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/statements` | Upload PDF (`file`, optional `password`) → processed statement |
| `GET` | `/statements` | Statement history (`limit`, `offset`) |
| `GET` | `/statements/{id}` | Statement details, PDF type, bank, account, confidence |
| `DELETE` | `/statements/{id}` | Delete statement and all its transactions |
| `GET` | `/statements/{id}/transactions` | Paginated/filterable rows with sorting |
| `PATCH` | `/transactions/{id}` | Update category, save override, apply to similar |
| `GET` | `/statements/{id}/summary` | Totals, category breakdown, monthly flow, merchants |
| `GET` | `/statements/{id}/export` | Download `format=xlsx\|csv` |
| `GET` | `/merge/export` | Merge multiple statements `ids=a,b,c` → `format=xlsx\|csv` |
| `GET` | `/categories` | Taxonomy with income/expense/transfer/neutral types |
| `GET` | `/rules` | Active YAML classification rules |
| `POST` | `/classify/retrain` | Append overrides and refit — returns accuracy |
| `GET` | `/health` | Liveness + OCR/model/database status |
| `GET` | `/info` | Version, OCR details, limits, privacy statement |

**Error shape:**
```json
{"detail": {"code": "NEEDS_PASSWORD", "message": "This PDF is password protected…"}}
```

Error codes: `INVALID_FILE`, `NEEDS_PASSWORD`, `NO_TRANSACTIONS_FOUND`, `OCR_FAILED`, `TOO_MANY_PAGES`, `FILE_TOO_LARGE`, `STATEMENT_NOT_FOUND`, `TRANSACTION_NOT_FOUND`, `INVALID_CATEGORY`, `RETRAIN_FAILED`.

---

## 📁 Project Layout

```
bank-statement-processor/
├── backend/
│   ├── app/
│   │   ├── api/              # Routes: upload, results, export, meta + serializers
│   │   ├── classification/   # Rule engine, YAML config, UPI parser, ML trainer
│   │   ├── core/             # PDF detector, text extractor, OCR, table reconstructor
│   │   │   └── bank_profiles/  # SBI, HDFC, ICICI, Axis, Generic profiles
│   │   ├── export/           # XLSX (with charts) and CSV exporters
│   │   ├── models/           # SQLAlchemy ORM models + Pydantic schemas
│   │   ├── config.py         # Environment-driven settings
│   │   ├── db.py             # Database session + engine
│   │   └── main.py           # FastAPI app, CORS, static SPA mount
│   ├── data/
│   │   ├── models/           # classifier.joblib (trained model)
│   │   └── training/         # transactions_labeled.csv
│   ├── tests/                # 66 pytest tests
│   └── requirements.txt
├── frontend/
│   ├── index.html            # SPA shell
│   ├── styles.css            # Premium UI design
│   └── app.js                # Vanilla JS (no build step)
├── samples/                  # Fixture PDFs + sample exports
├── scripts/                  # PDF / training data / export generators
├── docs/                     # Classifier metrics + confusion matrix
├── Dockerfile
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## 🏦 Adding a Bank Profile

Profiles are data, not algorithms. Create `backend/app/core/bank_profiles/mybank.py`:

```python
from app.core.bank_profiles.base import BankProfile

PROFILE = BankProfile(
    id="mybank",
    name="My Bank",
    ifsc_prefixes=("MYBK",),
    name_keywords=("MY BANK",),
    date_formats=("DD/MM/YYYY", "DD-MM-YYYY"),
    amount_style="separate",          # or "single_marker"
    extra_aliases={
        "description": ("transaction particulars",),
        "debit":       ("withdrawals",),
        "credit":      ("deposits",),
    },
    notes="My Bank retail statement.",
)
```

Then register it in `backend/app/core/bank_profiles/__init__.py` and add an IFSC entry to `base.py`.

Unknown banks fall back to `generic`, which infers columns from numeric-token x-position clustering.

---

## 🏷️ Classification Rules

Rules live in `backend/app/classification/rules_config.yaml` (reloaded at startup, no code change needed):

```yaml
- id: coffee_shops
  category: Food & Dining
  priority: 120
  direction: debit
  keywords: [CHAAYOS, THIRD WAVE, BLUE TOKAI]
  regex: ['@(?:OK|YBL)[A-Z]*']
  min_amount: 0
  max_amount: 2000
  reason: coffee shop
```

**Conflict resolution:** priority → match specificity (longer match) → direction.  
User overrides always win, then high-confidence rules (≥ 0.75), then ML, then `Uncategorized`.

---

## 🔄 Retraining the Classifier

**From the UI:** click **Retrain model** (`POST /api/classify/retrain`).

**From the CLI (inside `backend/`):**

```bash
# Rebuild the synthetic training corpus (optional)
..\\.venv\Scripts\python.exe ..\scripts\generate_training_data.py

# Train all candidates, compare by CV, write metrics to docs/
..\\.venv\Scripts\python.exe -m app.classification.train

# Quick refit including user overrides
..\\.venv\Scripts\python.exe -m app.classification.train --with-overrides --quick
```

**Current classifier performance** (348 samples, 28 classes):

| Metric | Value |
|---|---:|
| **Accuracy** | **99.71%** |
| **Macro F1** | **99.72%** |
| CV: Logistic Regression | 99.57% |
| CV: Linear SVM | 99.57% |
| CV: Multinomial NB | 97.48% |

> Target was ≥ 90%; achieved 99.71%.

---

## 🧪 Tests

```bash
cd backend
$env:PYTHONPATH = (Get-Location).Path           # PowerShell
# or: export PYTHONPATH="$PWD"                  # Bash

# Run all tests
..\\.venv\Scripts\python.exe -m pytest -q       # Windows
../.venv/bin/python -m pytest -q               # Linux/macOS
```

**Result: 66 passed** (OCR tests auto-skip when Tesseract is unavailable).

Coverage highlights:
- Date/amount normalisation (Indian grouping, Dr/Cr, parentheses, OCR digit fixes)
- Bank detection, header detection, multi-line row merging, borderless fallback
- Reconciliation, swap/spurious-column/OCR repair, dedupe, reverse chronology
- Rule engine, UPI parser, override precedence, ML smoke test
- CSV/XLSX structure and numeric/date cell types (opened with openpyxl)
- API: upload, history, filters, summary, PATCH, exports, merge, password, empty & invalid
- Full pipeline on text, scanned (OCR) and mixed fixtures with reconciliation

---

## 🔒 Privacy & Security

- **Zero external calls** — no AI APIs, no analytics, no telemetry
- Uploaded PDFs are deleted immediately after processing (`BSP_KEEP_UPLOADS=0`)
- Account numbers are masked in logs and UI
- CORS is permissive for local development — put behind a reverse proxy + auth before exposing beyond localhost

---

## ⚠️ Known Limitations

- Generic borderless fallback works best on English, left-to-right, single-table statements
- OCR accuracy depends on scan quality; low-DPI/faint scans are flagged but may need manual correction
- SQLite + synchronous processing is intended for single-user / demo scale
- Password-protected PDFs are decrypted in memory; the password is never stored
- No authentication or multi-tenancy (see Future improvements)

---

## 🔮 Future Improvements

- Table-detection models (LayoutLM / Table Transformer) as an optional local path
- More bank profiles and regional language OCR packs
- Async job queue (Celery/RQ) and background polling for large batches
- PostgreSQL + Alembic migrations for multi-user deployments
- Authentication, per-user isolation and audit logs
- Cloud OCR providers as an explicitly opt-in alternative
- Budgets, anomaly detection and month-over-month insights
- PDF page preview with row highlighting for review

---

## 🛠️ Troubleshooting

| Symptom | Fix |
|---|---|
| `Tesseract is not available` | Install Tesseract 5 and/or set `TESSERACT_CMD` |
| Scanned PDF returns `OCR_FAILED` | Check Tesseract language data: `tesseract --list-langs` |
| `Could not delete temporary upload` (Windows) | Parser briefly held the file; retried after GC — safe to ignore |
| Model missing warning | Run `python -m app.classification.train` |
| Port 8000 busy | Use `--port 8080` |
| Docker build fails on `libgl1` | On older Debian, use `libgl1-mesa-glx`; image uses Debian bookworm |
| Excel shows garbled `₹` | Use XLSX export (not CSV), or UTF-8-BOM CSV |

---

## 📜 License

This project is released for educational and personal use. For commercial use, please open an issue to discuss licensing.

---

<p align="center">
  Built with ❤️ using <strong>FastAPI</strong> · <strong>scikit-learn</strong> · <strong>pdfplumber</strong> · <strong>Tesseract</strong> · <strong>OpenCV</strong>
</p>
