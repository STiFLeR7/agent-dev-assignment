import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent

load_dotenv(BASE_DIR / ".env", override=True)
DATA_DIR = BASE_DIR
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

INVOICE_FILES = [
    DATA_DIR / "Invoice_1_Baseline.pdf",
    DATA_DIR / "Invoice_2_Scanned.pdf",
    DATA_DIR / "Invoice_3_Different_Format.pdf",
    DATA_DIR / "Invoice_4_Price_Trap.pdf",
    DATA_DIR / "Invoice_5_Missing_PO.pdf",
]

PO_DATABASE_FILE = DATA_DIR / "purchase_orders.json"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

class ReconciliationThresholds:
    
    
    PRICE_TOLERANCE_PERCENT = 2.0
    TOTAL_VARIANCE_AMOUNT = 5.0
    TOTAL_VARIANCE_PERCENT = 1.0
    MIN_EXTRACTION_CONFIDENCE = 0.90
    
    PRICE_VARIANCE_REVIEW_MIN = 5.0
    PRICE_VARIANCE_REVIEW_MAX = 15.0
    FUZZY_MATCH_MIN_CONFIDENCE = 0.70
    LOW_EXTRACTION_CONFIDENCE_MIN = 0.70
    LOW_EXTRACTION_CONFIDENCE_MAX = 0.89
    
    PRICE_VARIANCE_ESCALATE = 15.0
    NO_MATCH_CONFIDENCE = 0.50
    TOTAL_VARIANCE_ESCALATE = 10.0
    MAX_DISCREPANCIES_BEFORE_ESCALATE = 3
    VERY_LOW_CONFIDENCE = 0.70
    
    DATE_RANGE_DAYS = 14
    PRODUCT_MATCH_THRESHOLD = 0.70
    PRODUCT_ONLY_MATCH_THRESHOLD = 0.80

class ConfidenceScoring:
    
    
    EXACT_PO_MATCH = (0.95, 0.99)
    FUZZY_SUPPLIER_PRODUCT_DATE = (0.60, 0.85)
    PRODUCT_ONLY_FUZZY = (0.40, 0.70)
    
    GOOD_QUALITY = (0.90, 0.95)
    ACCEPTABLE_QUALITY = (0.75, 0.85)
    POOR_QUALITY = (0.50, 0.70)

AGENT_CONFIG = {
    "document_intelligence": {
        "name": "Document Intelligence Agent",
        "description": "Extracts structured data from invoice PDFs",
        "timeout_seconds": 60,
    },
    "matching": {
        "name": "Matching Agent", 
        "description": "Matches invoices to PO database",
        "timeout_seconds": 30,
    },
    "discrepancy_detection": {
        "name": "Discrepancy Detection Agent",
        "description": "Flags price/quantity mismatches",
        "timeout_seconds": 30,
    },
    "resolution": {
        "name": "Resolution Recommendation Agent",
        "description": "Recommends actions based on findings",
        "timeout_seconds": 30,
    },
}
