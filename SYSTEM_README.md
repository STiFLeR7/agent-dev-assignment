# Invoice Reconciliation Multi-Agent System

A production-grade multi-agent system that processes supplier invoices, extracts structured data, matches against purchase orders, and intelligently flags discrepancies.

## 🏗️ Architecture

This system implements a **LangGraph-based multi-agent workflow** with four specialized agents:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Invoice Reconciliation Workflow               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌───────────────────┐                                         │
│   │  Invoice PDF      │                                         │
│   └─────────┬─────────┘                                         │
│             │                                                    │
│             ▼                                                    │
│   ┌───────────────────────────────────────┐                     │
│   │  1. Document Intelligence Agent       │ ◄── GPT-4o Vision   │
│   │     - PDF to image conversion         │                     │
│   │     - OCR for scanned docs            │                     │
│   │     - Structured data extraction      │                     │
│   │     - Confidence scoring              │                     │
│   └─────────┬─────────────────────────────┘                     │
│             │                                                    │
│             ▼                                                    │
│   ┌───────────────────────────────────────┐                     │
│   │  2. Matching Agent                    │                     │
│   │     - Exact PO reference matching     │                     │
│   │     - Fuzzy supplier/product matching │                     │
│   │     - Confidence-based ranking        │                     │
│   └─────────┬─────────────────────────────┘                     │
│             │                                                    │
│             ▼                                                    │
│   ┌───────────────────────────────────────┐                     │
│   │  3. Discrepancy Detection Agent       │                     │
│   │     - Price variance detection        │                     │
│   │     - Quantity mismatch flagging      │                     │
│   │     - Total variance analysis         │                     │
│   └─────────┬─────────────────────────────┘                     │
│             │                                                    │
│             ▼                                                    │
│   ┌───────────────────────────────────────┐                     │
│   │  4. Resolution Recommendation Agent   │                     │
│   │     - Risk assessment                 │                     │
│   │     - Action recommendation           │                     │
│   │     - Reasoning transparency          │                     │
│   └─────────┬─────────────────────────────┘                     │
│             │                                                    │
│             ▼                                                    │
│   ┌───────────────────┐                                         │
│   │  JSON Output      │                                         │
│   └───────────────────┘                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- OpenAI API key with GPT-4o access
- (Optional) Poppler for PDF processing on Windows

### Installation

1. **Clone and navigate to the project:**
   ```bash
   cd agent-dev
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   # Copy the example .env file
   cp .env.example .env
   
   # Edit .env and add your OpenAI API key
   OPENAI_API_KEY=sk-your-key-here
   ```

### Running the System

**Process all 5 test invoices:**
```bash
python -m src.main
```

**Process a single invoice:**
```bash
python -m src.main --invoice Invoice_1_Baseline.pdf
```

**With verbose output:**
```bash
python -m src.main --verbose
```

**Save results to specific file:**
```bash
python -m src.main --output results.json
```

## 📁 Project Structure

```
agent-dev/
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── config.py            # Configuration & thresholds
│   ├── models.py            # Pydantic data models
│   ├── orchestrator.py      # LangGraph workflow
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── document_intelligence.py  # PDF extraction agent
│   │   ├── matching.py               # PO matching agent
│   │   ├── discrepancy_detection.py  # Discrepancy agent
│   │   └── resolution.py             # Recommendation agent
│   └── utils/
│       ├── __init__.py
│       ├── pdf_utils.py     # PDF processing utilities
│       └── matching_utils.py # Fuzzy matching utilities
├── output/                   # Results JSON files
├── Invoice_1_Baseline.pdf    # Test invoices
├── Invoice_2_Scanned.pdf
├── Invoice_3_Different_Format.pdf
├── Invoice_4_Price_Trap.pdf
├── Invoice_5_Missing_PO.pdf
├── purchase_orders.json      # PO database
├── requirements.txt
├── .env.example
└── README.md
```

## 📋 Test Invoices

| Invoice | Difficulty | Challenge | Expected Result |
|---------|------------|-----------|-----------------|
| Invoice 1 | Easy | Clean PDF, perfect match | ✅ Auto-approve |
| Invoice 2 | Medium | Scanned, rotated | ✅/🔶 Based on OCR quality |
| Invoice 3 | Medium-Hard | Different template | ✅/🔶 Template-agnostic matching |
| Invoice 4 | **Critical** | 10% price increase on Ibuprofen | 🔶 Flag for review |
| Invoice 5 | **Critical** | No PO reference | 🔶 Fuzzy match to PO-2024-005 |

## 🔧 Configuration

Key thresholds in `src/config.py`:

```python
# Auto-approve criteria
PRICE_TOLERANCE_PERCENT = 2.0      # ±2% for auto-approve
MIN_EXTRACTION_CONFIDENCE = 0.90   # 90% minimum

# Flag for review
PRICE_VARIANCE_REVIEW_MIN = 5.0    # >5% triggers review
PRICE_VARIANCE_REVIEW_MAX = 15.0   # ≤15% stays in review

# Escalation
PRICE_VARIANCE_ESCALATE = 15.0     # >15% escalate
NO_MATCH_CONFIDENCE = 0.50         # <50% escalate
```

## 📊 Output Format

Results are saved as JSON:

```json
{
  "invoice_id": "INV-2024-1001",
  "processing_timestamp": "2024-01-29T10:15:32Z",
  "processing_results": {
    "extraction_confidence": 0.97,
    "document_quality": "excellent",
    "extracted_data": { ... },
    "matching_results": {
      "matched_po": "PO-2024-001",
      "po_match_confidence": 0.99,
      "match_method": "exact_po_reference"
    },
    "discrepancies": [ ... ],
    "recommended_action": "auto_approve",
    "agent_reasoning": "..."
  }
}
```

## 🧪 Critical Tests

### Invoice 4: Price Trap
- **Challenge:** Ibuprofen priced at £88 instead of £80 (10% increase)
- **Expected:** System should detect and flag for review
- **Validation:** Check `discrepancies` array for `price_mismatch` entry

### Invoice 5: Missing PO
- **Challenge:** No PO reference on invoice
- **Expected:** Fuzzy match to PO-2024-005 via supplier + products
- **Validation:** Check `matched_po` shows correct PO despite missing reference

## 🤖 Agent Decision Flow

1. **Document Intelligence Agent**
   - Converts PDF to images
   - Uses GPT-4o Vision for extraction
   - Outputs structured data with confidence scores

2. **Matching Agent**
   - First tries exact PO reference match
   - Falls back to supplier + date + products fuzzy match
   - Last resort: product-only matching

3. **Discrepancy Detection Agent**
   - Compares every line item
   - Calculates price/quantity variances
   - Flags issues with severity levels

4. **Resolution Agent**
   - Synthesizes all findings
   - Applies business rules
   - Recommends: auto_approve | flag_for_review | escalate_to_human

## 📝 License

MIT License - Built for NIYAMRAI Agent Development Assessment
