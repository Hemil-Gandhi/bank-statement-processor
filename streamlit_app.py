"""LedgerLens — Bank Statement Processor (Streamlit UI)."""
from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path
from decimal import Decimal

import streamlit as st

# ── Bootstrap backend path ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.db import get_db, init_db  # noqa: E402
from app.core.pipeline import process_statement  # noqa: E402
from app.core.errors import PipelineError  # noqa: E402
from app.models.db_models import StatementJob  # noqa: E402

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LedgerLens · Bank Statement Processing",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
}

/* Hide default streamlit header / footer */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }

/* Metric cards */
[data-testid="metric-container"] {
    background: white;
    border: 1px solid rgba(79,70,229,0.12);
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 2px 10px rgba(13,15,28,0.07);
    transition: box-shadow 0.2s, transform 0.2s;
}
[data-testid="metric-container"]:hover {
    box-shadow: 0 8px 28px rgba(13,15,28,0.12);
    transform: translateY(-2px);
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    font-size: 10px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.9px !important;
    color: #6B6E92 !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 22px !important;
    font-weight: 800 !important;
    color: #0D0F1C !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #0D0F1C !important;
    background-image: radial-gradient(ellipse at 20% 0%, rgba(79,70,229,0.18) 0%, transparent 60%),
                      radial-gradient(ellipse at 80% 100%, rgba(124,58,237,0.12) 0%, transparent 50%) !important;
}
[data-testid="stSidebar"] * { color: rgba(255,255,255,0.75) !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #fff !important; }
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stFileUploader label { color: rgba(255,255,255,0.55) !important; font-size: 10px !important; letter-spacing: 0.8px !important; text-transform: uppercase !important; }

/* Primary buttons */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    padding: 10px 20px !important;
    box-shadow: 0 4px 22px rgba(79,70,229,0.3) !important;
    transition: all 0.2s !important;
}
.stButton > button[kind="primary"]:hover {
    filter: brightness(1.1) !important;
    transform: translateY(-1px) !important;
}
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    overflow: hidden;
    box-shadow: 0 2px 10px rgba(13,15,28,0.07);
}

/* Upload area */
[data-testid="stFileUploaderDropzone"] {
    border: 2px dashed rgba(79,70,229,0.35) !important;
    border-radius: 14px !important;
    background: linear-gradient(135deg, rgba(79,70,229,0.06) 0%, rgba(124,58,237,0.04) 100%) !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: rgba(79,70,229,0.7) !important;
    background: rgba(79,70,229,0.08) !important;
}

/* Section headers */
h1 { font-weight: 800 !important; letter-spacing: -0.5px !important; }
h2 { font-weight: 700 !important; letter-spacing: -0.3px !important; }
h3 { font-weight: 700 !important; }

/* Info boxes */
.stAlert { border-radius: 10px !important; }

/* Tab styling */
[data-testid="stTab"] { font-weight: 600 !important; }

/* Download button */
.stDownloadButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    border-color: rgba(79,70,229,0.3) !important;
}
.stDownloadButton > button:hover {
    border-color: #4F46E5 !important;
    color: #4F46E5 !important;
}
</style>
""", unsafe_allow_html=True)

# ── DB init ───────────────────────────────────────────────────────────────────
@st.cache_resource
def _init_db():
    init_db()

_init_db()


def _get_session():
    gen = get_db()
    return next(gen)


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_money(val, currency="INR") -> str:
    if val is None:
        return "—"
    try:
        import locale
        return f"₹{float(val):,.2f}"
    except Exception:
        return str(val)


def fmt_pct(val) -> str:
    if val is None:
        return "—"
    return f"{float(val)*100:.1f}%"


def _build_df(transactions):
    import pandas as pd
    rows = []
    for txn in transactions:
        rows.append({
            "Date": str(txn.txn_date),
            "Description": txn.description,
            "Debit (₹)": float(txn.debit) if txn.debit is not None else None,
            "Credit (₹)": float(txn.credit) if txn.credit is not None else None,
            "Balance (₹)": float(txn.balance) if txn.balance is not None else None,
            "Category": txn.category or "—",
            "Source": txn.category_source or "—",
            "Confidence": f"{float(txn.category_confidence or 0)*100:.0f}%",
            "Flags": ", ".join(txn.flags) if txn.flags else "",
        })
    return pd.DataFrame(rows)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:12px;padding-bottom:20px;border-bottom:1px solid rgba(255,255,255,0.1);margin-bottom:16px;">
        <div style="width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,#4F46E5,#7C3AED);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px;color:white;box-shadow:0 4px 16px rgba(79,70,229,0.5);">LL</div>
        <div>
            <div style="font-size:15px;font-weight:700;color:white;">LedgerLens</div>
            <div style="font-size:10px;color:rgba(255,255,255,0.4);letter-spacing:0.3px;">Statement Processing</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "Navigation",
        ["Upload & Process", "History", "About"],
        label_visibility="collapsed",
    )

    st.markdown("<hr style='border-color:rgba(255,255,255,0.08);margin:16px 0;'>", unsafe_allow_html=True)

    # System status
    st.markdown("<div style='font-size:9px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:rgba(255,255,255,0.3);margin-bottom:8px;'>System Status</div>", unsafe_allow_html=True)
    try:
        from app.core.ocr_extractor import ocr_available
        from app.classification.ml_model import model_available
        ocr_ok = ocr_available()
        model_ok = model_available()
    except Exception:
        ocr_ok = False
        model_ok = False

    def _status_row(label, ok, value):
        dot_color = "#34D399" if ok else "#F87171"
        return f"""<div style="display:flex;align-items:center;gap:8px;font-size:11px;color:rgba(255,255,255,0.5);padding:4px 0;">
            <div style="width:7px;height:7px;border-radius:50%;background:{dot_color};box-shadow:0 0 6px {dot_color}44;flex-shrink:0;"></div>
            <span>{label}</span>
            <span style="margin-left:auto;font-weight:600;font-size:10px;color:rgba(255,255,255,0.7);">{value}</span>
        </div>"""

    st.markdown(
        _status_row("API", True, "online") +
        _status_row("OCR", ocr_ok, "ready" if ocr_ok else "off") +
        _status_row("ML Model", model_ok, "ready" if model_ok else "off") +
        _status_row("Privacy", True, "local only"),
        unsafe_allow_html=True,
    )


# ── Page: Upload & Process ────────────────────────────────────────────────────
if page == "Upload & Process":
    st.markdown("## Bank Statement Processing")
    st.markdown("<p style='color:#6B6E92;margin-top:-8px;margin-bottom:24px;'>Upload a PDF bank statement to extract, classify and analyse transactions.</p>", unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Drop PDF files here or click to browse",
        type=["pdf"],
        accept_multiple_files=False,
        help="Supported: text PDFs, scanned PDFs (OCR), password-protected PDFs. Max 25 MB.",
    )

    password = None
    if uploaded:
        with st.expander("Password-protected PDF?", expanded=False):
            password = st.text_input("Enter PDF password (leave blank if none)", type="password")

    if uploaded:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"**Selected:** `{uploaded.name}` ({uploaded.size / 1024:.1f} KB)")
        with col2:
            process_btn = st.button("Process Statement", type="primary", use_container_width=True)

        if process_btn:
            with st.spinner("Extracting transactions... this may take a moment for scanned PDFs."):
                try:
                    data = uploaded.read()
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(data)
                        tmp_path = Path(tmp.name)

                    session = _get_session()
                    result = process_statement(
                        tmp_path,
                        uploaded.name,
                        session,
                        password=password or None,
                    )
                    tmp_path.unlink(missing_ok=True)
                    st.session_state["result"] = result
                    st.session_state["session"] = session
                    st.success(f"Processed {len(result.transactions)} transactions in {result.duration_ms} ms")
                except PipelineError as e:
                    st.error(f"Processing failed: {e.message}")
                    st.stop()
                except Exception as e:
                    st.error(f"Unexpected error: {e}")
                    st.stop()

    # ── Results ──────────────────────────────────────────────────────────────
    if "result" in st.session_state:
        result = st.session_state["result"]
        acc = result.account
        val = result.validation
        txns = result.transactions

        st.markdown("---")

        # Header row
        hcol1, hcol2 = st.columns([3, 1])
        with hcol1:
            bank_initial = (result.bank.bank_name or "B")[0].upper()
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:14px;margin-bottom:8px;">
                <div style="width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,#4F46E5,#7C3AED);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:white;box-shadow:0 4px 16px rgba(79,70,229,0.4);">{bank_initial}</div>
                <div>
                    <div style="font-size:18px;font-weight:800;color:#0D0F1C;">{result.filename}</div>
                    <div style="font-size:12px;color:#6B6E92;">{result.bank.bank_name} · {result.detection.num_pages} pages · {result.duration_ms} ms</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        with hcol2:
            pdf_type_color = {"TEXT": "#2563EB", "IMAGE": "#D97706", "MIXED": "#4F46E5"}.get(result.detection.pdf_type, "#6B6E92")
            st.markdown(f'<span style="background:rgba(79,70,229,0.1);color:#4F46E5;border-radius:7px;padding:4px 12px;font-size:11px;font-weight:700;">{result.detection.pdf_type} PDF</span>', unsafe_allow_html=True)

        # KPI metrics
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Transactions", f"{len(txns):,}")
        m2.metric("Total Debits", fmt_money(val.total_debit))
        m3.metric("Total Credits", fmt_money(val.total_credit))
        m4.metric("Net Movement", fmt_money(val.total_credit - val.total_debit))
        m5.metric("Confidence", fmt_pct(val.extraction_confidence))

        # Account details
        with st.expander("Account Details", expanded=True):
            ac1, ac2, ac3, ac4 = st.columns(4)
            ac1.markdown(f"**Account Holder**  \n{acc.account_holder_name or '—'}")
            ac2.markdown(f"**Bank**  \n{result.bank.bank_name or '—'}")
            ac3.markdown(f"**Period**  \n{acc.statement_period_from or '—'} → {acc.statement_period_to or '—'}")
            ac4.markdown(f"**Opening / Closing**  \n{fmt_money(acc.opening_balance)} / {fmt_money(acc.closing_balance)}")

        # Warnings
        if result.warnings:
            with st.expander(f"Warnings ({len(result.warnings)})", expanded=False):
                for w in result.warnings:
                    st.warning(w.replace("_", " ").capitalize())

        # Tabs
        tab1, tab2, tab3 = st.tabs(["Transactions", "Dashboard", "Export"])

        with tab1:
            import pandas as pd
            df = _build_df(txns)

            # Filters
            fc1, fc2, fc3, fc4 = st.columns(4)
            search = fc1.text_input("Search", placeholder="Description...")
            cat_options = ["All"] + sorted(df["Category"].unique().tolist())
            cat_filter = fc2.selectbox("Category", cat_options)
            type_filter = fc3.selectbox("Type", ["Both", "Debit only", "Credit only"])
            sort_by = fc4.selectbox("Sort", ["Date", "Debit ↓", "Credit ↓"])

            filtered = df.copy()
            if search:
                filtered = filtered[filtered["Description"].str.contains(search, case=False, na=False)]
            if cat_filter != "All":
                filtered = filtered[filtered["Category"] == cat_filter]
            if type_filter == "Debit only":
                filtered = filtered[filtered["Debit (₹)"].notna()]
            elif type_filter == "Credit only":
                filtered = filtered[filtered["Credit (₹)"].notna()]
            if sort_by == "Debit ↓":
                filtered = filtered.sort_values("Debit (₹)", ascending=False)
            elif sort_by == "Credit ↓":
                filtered = filtered.sort_values("Credit (₹)", ascending=False)

            st.markdown(f"<small style='color:#6B6E92;'>{len(filtered):,} of {len(df):,} transactions</small>", unsafe_allow_html=True)
            st.dataframe(
                filtered,
                use_container_width=True,
                height=480,
                column_config={
                    "Debit (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                    "Credit (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                    "Balance (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                },
            )

        with tab2:
            import pandas as pd

            df = _build_df(txns)
            df["Debit (₹)"] = pd.to_numeric(df["Debit (₹)"], errors="coerce")
            df["Credit (₹)"] = pd.to_numeric(df["Credit (₹)"], errors="coerce")
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df["Month"] = df["Date"].dt.to_period("M").astype(str)

            d1, d2 = st.columns(2)

            with d1:
                st.markdown("#### Spend by Category")
                cat_spend = (
                    df[df["Debit (₹)"].notna()]
                    .groupby("Category")["Debit (₹)"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(10)
                    .reset_index()
                )
                cat_spend.columns = ["Category", "Total Spend (₹)"]
                st.bar_chart(cat_spend.set_index("Category"), color="#4F46E5")

            with d2:
                st.markdown("#### Monthly Cash Flow")
                monthly = df.groupby("Month").agg(
                    Debits=("Debit (₹)", "sum"),
                    Credits=("Credit (₹)", "sum"),
                ).reset_index().sort_values("Month")
                st.bar_chart(monthly.set_index("Month")[["Credits", "Debits"]])

            st.markdown("#### Running Balance")
            if df["Balance (₹)"].notna().any():
                bal_df = df[df["Balance (₹)"].notna()][["Date", "Balance (₹)"]].sort_values("Date")
                st.line_chart(bal_df.set_index("Date"), color="#4F46E5")
            else:
                st.info("Balance data not available in this statement.")

            st.markdown("#### Top Merchants by Spend")
            top_m = (
                df[df["Debit (₹)"].notna()]
                .groupby("Description")["Debit (₹)"]
                .sum()
                .sort_values(ascending=False)
                .head(10)
                .reset_index()
            )
            top_m.columns = ["Merchant", "Spend (₹)"]
            st.dataframe(top_m, use_container_width=True, hide_index=True)

        with tab3:
            import pandas as pd
            df = _build_df(txns)

            st.markdown("#### Export Transactions")
            ecol1, ecol2 = st.columns(2)

            with ecol1:
                csv_buf = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="Download CSV",
                    data=csv_buf,
                    file_name=f"{result.filename.replace('.pdf', '')}_transactions.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with ecol2:
                xlsx_buf = io.BytesIO()
                with pd.ExcelWriter(xlsx_buf, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Transactions")
                    # Summary sheet
                    summary_data = {
                        "Field": ["Bank", "Account Holder", "Period", "Opening Balance", "Closing Balance",
                                  "Total Transactions", "Total Debits", "Total Credits", "Confidence"],
                        "Value": [
                            result.bank.bank_name,
                            acc.account_holder_name or "—",
                            f"{acc.statement_period_from} to {acc.statement_period_to}",
                            fmt_money(acc.opening_balance),
                            fmt_money(acc.closing_balance),
                            len(txns),
                            fmt_money(val.total_debit),
                            fmt_money(val.total_credit),
                            fmt_pct(val.extraction_confidence),
                        ]
                    }
                    pd.DataFrame(summary_data).to_excel(writer, index=False, sheet_name="Summary")
                xlsx_buf.seek(0)
                st.download_button(
                    label="Download Excel",
                    data=xlsx_buf,
                    file_name=f"{result.filename.replace('.pdf', '')}_transactions.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

            st.markdown(f"""
            <div style="margin-top:16px;padding:14px 18px;background:rgba(79,70,229,0.06);border:1px solid rgba(79,70,229,0.15);border-radius:10px;font-size:12px;color:#6B6E92;">
                Exporting <strong style="color:#0D0F1C;">{len(df):,} rows</strong> from <strong style="color:#0D0F1C;">{result.filename}</strong>.
                Files are processed locally — no data is sent to any server.
            </div>
            """, unsafe_allow_html=True)


# ── Page: History ─────────────────────────────────────────────────────────────
elif page == "History":
    st.markdown("## Statement History")
    st.markdown("<p style='color:#6B6E92;margin-top:-8px;margin-bottom:24px;'>Previously processed statements stored in this session.</p>", unsafe_allow_html=True)

    try:
        session = _get_session()
        jobs = session.query(StatementJob).order_by(StatementJob.created_at.desc()).limit(50).all()
        if not jobs:
            st.info("No statements processed yet. Go to Upload & Process to get started.")
        else:
            import pandas as pd
            rows = []
            for job in jobs:
                stats = job.stats or {}
                rows.append({
                    "Filename": job.filename,
                    "Bank": job.bank_detected or "—",
                    "Type": job.pdf_type or "—",
                    "Pages": job.num_pages,
                    "Transactions": int(stats.get("transaction_count", 0)),
                    "Confidence": fmt_pct(job.extraction_confidence),
                    "Processed": str(job.created_at)[:19] if job.created_at else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Could not load history: {e}")


# ── Page: About ───────────────────────────────────────────────────────────────
elif page == "About":
    st.markdown("## About LedgerLens")

    st.markdown("""
    **LedgerLens** is a local, private bank statement processing tool.

    - Extracts transactions from text and scanned (OCR) PDF bank statements
    - Supports Indian bank formats — SBI, HDFC, ICICI, Axis, Kotak and more
    - Classifies transactions using rules + TF-IDF ML — no LLM, no external AI
    - Reconciles balances row-by-row for accuracy
    - Exports to CSV and Excel

    ### Privacy
    All processing happens locally. No files are uploaded to any external service.
    Uploaded PDFs are deleted immediately after processing.

    ### Tech Stack
    - **Processing:** PyMuPDF, pdfplumber, Tesseract OCR
    - **Classification:** scikit-learn TF-IDF + rule engine
    - **UI:** Streamlit
    - **Storage:** SQLite (local session)
    """)

    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Supported Banks", "15+")
    c2.metric("Max File Size", "25 MB")
    c3.metric("Max Pages", "100")
