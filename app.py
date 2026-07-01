"""
app.py — Streamlit UI for the receipt-to-spreadsheet extractor.

Run:  streamlit run app.py
"""

import io
import os

import anthropic
import pandas as pd
import streamlit as st

from extractor import FIELD_ORDER, extract_receipt

st.set_page_config(page_title="Receipt to Spreadsheet", page_icon="🧾", layout="wide")

MODELS = {
    "Claude Sonnet 4.6 — balanced (default)": "claude-sonnet-4-6",
    "Claude Haiku 4.5 — cheapest & fastest": "claude-haiku-4-5",
    "Claude Opus 4.8 — most accurate": "claude-opus-4-8",
}

# --- Sidebar: configuration -------------------------------------------------
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input(
        "Anthropic API key",
        type="password",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        help="Starts with sk-ant-. Get one at console.anthropic.com. "
        "You can also set the ANTHROPIC_API_KEY environment variable.",
    )
    model_label = st.selectbox("Model", list(MODELS.keys()), index=0)
    model = MODELS[model_label]
    st.caption(
        "Haiku is cheapest for large batches, Sonnet is a good default, "
        "and Opus handles faded or handwritten receipts best."
    )

# --- Header -----------------------------------------------------------------
st.title("🧾 Receipt → Spreadsheet")
st.write(
    "Drop in a pile of receipt photos or PDFs. Claude reads each one and turns "
    "it into a clean, editable spreadsheet — no manual data entry."
)

# --- Upload -----------------------------------------------------------------
uploaded = st.file_uploader(
    "Upload receipts (PNG, JPG, WEBP, or PDF)",
    type=["png", "jpg", "jpeg", "webp", "pdf"],
    accept_multiple_files=True,
)

run = st.button("Extract", type="primary", disabled=not uploaded)

if "rows" not in st.session_state:
    st.session_state.rows = None

if run:
    if not api_key:
        st.error("Please enter your Anthropic API key in the sidebar first.")
        st.stop()

    client = anthropic.Anthropic(api_key=api_key)
    rows = []
    progress = st.progress(0.0, text="Starting…")
    total_files = len(uploaded)
    for i, f in enumerate(uploaded, start=1):
        progress.progress(i / total_files, text=f"Reading {f.name} ({i}/{total_files})…")
        result = extract_receipt(client, f.getvalue(), f.name, model=model)
        rows.append(result.as_row())
    progress.empty()
    st.session_state.rows = rows

# --- Results ----------------------------------------------------------------
if st.session_state.rows:
    df = pd.DataFrame(st.session_state.rows)
    ordered = ["source_file"] + FIELD_ORDER + ["error"]
    df = df[[c for c in ordered if c in df.columns]]

    n_errors = int(df["error"].notna().sum()) if "error" in df.columns else 0
    if n_errors:
        st.warning(f"{n_errors} file(s) could not be processed — see the 'error' column.")

    st.subheader("Review & edit")
    st.caption(
        "Claude gives a strong first pass, not the final word. "
        "Fix any cell directly in the table before exporting."
    )
    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic", key="editor")

    # Summary metrics
    totals = pd.to_numeric(edited["total"], errors="coerce") if "total" in edited else pd.Series(dtype=float)
    m1, m2, m3 = st.columns(3)
    m1.metric("Receipts", len(edited))
    m2.metric("Total spend", f"{totals.sum():,.2f}")
    low_conf = int((edited["confidence"] == "low").sum()) if "confidence" in edited else 0
    m3.metric("Low-confidence rows", low_conf)

    # Spend by category
    if "category" in edited and not totals.empty:
        by_cat = (
            pd.DataFrame({"category": edited["category"].fillna("Uncategorized"), "total": totals})
            .groupby("category")["total"]
            .sum()
            .sort_values(ascending=False)
        )
        if by_cat.abs().sum() > 0:
            st.subheader("Spend by category")
            st.bar_chart(by_cat)

    # Downloads
    csv_bytes = edited.to_csv(index=False).encode("utf-8")
    xlsx_buffer = io.BytesIO()
    with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
        edited.to_excel(writer, index=False, sheet_name="Receipts")

    d1, d2 = st.columns(2)
    d1.download_button("⬇ Download CSV", csv_bytes, "receipts.csv", "text/csv")
    d2.download_button(
        "⬇ Download Excel",
        xlsx_buffer.getvalue(),
        "receipts.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
