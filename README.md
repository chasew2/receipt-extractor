# 🧾 Receipt → Spreadsheet

**Turn a pile of receipt photos into a clean, exportable spreadsheet in seconds — no manual data entry.**

Upload receipt images or PDFs, and Claude reads each one and pulls out the vendor, date, amounts, tax, payment method, and a best-guess expense category. Results land in an editable table you review and correct, then export to Excel or CSV.

---

## Demo Video


https://github.com/user-attachments/assets/05a5d420-e92b-4129-86a6-727a0a5711d5



## The problem it solves

Expense tracking at most small companies is a manual chore: someone squints at a shoebox of receipts and retypes each one into a spreadsheet. It's slow, boring, and error-prone — exactly the kind of repetitive task that quietly eats hours every month. This tool replaces that data entry with a vision model, while keeping a human in the loop for the final sign-off.

## What it does

- **Reads images and PDFs** — phone photos, scans, or PDF invoices, in a single batch.
- **Extracts structured fields** — vendor, date, subtotal, tax, total, currency, payment method, line-item summary, and an auto-suggested expense category.
- **Flags shaky reads** — every row carries a confidence level, so blurry or ambiguous receipts get surfaced for review instead of silently guessed.
- **Keeps a human in the loop** — results open in an editable table; fix any cell before exporting.
- **Summarizes spend** — running total and a spend-by-category chart.
- **Exports** — one click to Excel or CSV.

## How it works

```
Receipt image / PDF
        │
        ▼
  Streamlit UI  ──►  Claude API (vision)  ──►  structured JSON (via tool use)
        │                                              │
        ▼                                              ▼
  Editable review table  ◄─────────────────  one row per receipt
        │
        ▼
  Export to Excel / CSV
```

The interesting engineering choice is how the structured data comes back. Rather than asking Claude for JSON in a prompt and hoping the string parses, the app defines the target schema as a **tool** and forces the model to call it. Every response is then guaranteed to be valid JSON in exactly the expected shape, which removes a whole category of brittle parsing bugs.

## Run it locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Provide your Anthropic API key (or paste it into the app's sidebar)
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Launch
streamlit run app.py
```

Then drag in the sample receipts under `samples/` to try it immediately. You'll need an Anthropic API key from [console.anthropic.com](https://console.anthropic.com); a batch of receipts costs a fraction of a cent each on the default model.

## Design decisions

- **Tool use over prompt-and-parse.** Forcing a tool call makes the output schema-guaranteed, so the UI never has to defend against malformed model output.
- **Human-in-the-loop by default.** A finance tool that silently miscategorizes an expense is worse than useless. The editable table treats the model as a fast first draft, not the final authority — which is also what makes it safe for a non-technical teammate to use.
- **Model is swappable.** Haiku for cheap high-volume batches, Sonnet as the balanced default, Opus for faded or handwritten receipts. Same code, one dropdown.
- **UI and logic are separated.** `extractor.py` holds the Claude call and schema; `app.py` is just the interface. The extraction logic is unit-testable without a running UI.

## Project layout

```
receipt_extractor/
├── app.py            # Streamlit UI
├── extractor.py      # Claude API call + schema (the core logic)
├── requirements.txt
├── .env.example
└── samples/          # two synthetic receipts to test with
```

## Where I'd take it next

- Persist results to a database so receipts accumulate over time instead of per-session.
- Push straight into Google Sheets or QuickBooks via their APIs.
- Duplicate detection (same vendor + date + total).
- Multi-page invoices with per-line-item breakdowns.
- A simple approval workflow: flag low-confidence rows to a reviewer automatically.
