import json
from typing import Optional
from datetime import datetime
from pathlib import Path

from ..models import (
    ExtractionResult,
    ExtractedInvoiceData,
    ExtractedLineItem,
    DocumentQuality,
    BillTo,
)
from ..utils.pdf_utils import pdf_to_base64_images, get_pdf_info
from ..utils.gemini_client import GeminiClient
from ..config import GEMINI_API_KEY, GEMINI_MODEL

EXTRACTION_PROMPT = """You are an expert invoice data extraction system. Analyze the provided invoice image and extract all relevant information into a structured JSON format.

Extract the following fields:
- invoice_number: The unique invoice identifier
- invoice_date: Date of the invoice (format: YYYY-MM-DD if possible)
- supplier_name: Name of the company issuing the invoice
- supplier_address: Full address of the supplier
- supplier_vat: VAT/Tax registration number of supplier
- po_reference: Purchase Order reference number (if present)
- payment_terms: Payment terms mentioned on invoice
- bill_to: Object with company name and address of the recipient
- line_items: Array of items with:
  - item_code: Product/item code
  - description: Item description
  - quantity: Number of units
  - unit: Unit of measurement
  - unit_price: Price per unit
  - line_total: Total for this line
- subtotal: Sum before tax
- vat_rate: VAT/Tax percentage
- vat_amount: VAT/Tax amount
- total: Final total amount
- currency: Currency code (GBP, USD, EUR, etc.)
- confidence_assessment: Your confidence level (high/medium/low)
- extraction_notes: Any notes about extraction quality or issues

Return ONLY valid JSON with these fields. If a field cannot be found, use null.
Be extremely careful with numbers - extract exact values as shown on the invoice."""

class DocumentIntelligenceAgent:
    
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL
        self.client = GeminiClient(api_key=self.api_key, model=self.model)
        self.name = "Document Intelligence Agent"
    
    def process(self, invoice_path: str) -> ExtractionResult:
        
        start_time = datetime.now()
        
        pdf_info = get_pdf_info(invoice_path)
        
        images = pdf_to_base64_images(invoice_path, dpi=200)
        
        if not images:
            raise ValueError(f"Could not extract images from PDF: {invoice_path}")
        
        raw_data = self.client.extract_invoice_data(
            images=images,
            extraction_prompt=EXTRACTION_PROMPT,
        )
        
        extracted_data = self._parse_extraction(raw_data)
        
        quality = self._assess_quality(raw_data, pdf_info)
        confidence = self._calculate_confidence(raw_data, extracted_data)
        
        field_confidences = self._build_field_confidences(raw_data, extracted_data)
        
        reasoning = self._build_reasoning(raw_data, extracted_data, quality, confidence)
        
        warnings = self._collect_warnings(raw_data, extracted_data)
        
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return ExtractionResult(
            extracted_data=extracted_data,
            extraction_confidence=confidence,
            document_quality=quality,
            field_confidences=field_confidences,
            agent_reasoning=reasoning,
            warnings=warnings,
        )
    
    def _parse_float(self, value) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace(',', '').replace(' ', '').strip()
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0
    
    def _parse_extraction(self, raw_data: dict) -> ExtractedInvoiceData:
        
        line_items = []
        for item in raw_data.get("line_items", []):
            line_items.append(ExtractedLineItem(
                item_code=item.get("item_code"),
                description=item.get("description", "Unknown"),
                quantity=self._parse_float(item.get("quantity", 0)),
                unit=item.get("unit", "units"),
                unit_price=self._parse_float(item.get("unit_price", 0)),
                line_total=self._parse_float(item.get("line_total", 0)),
            ))
        
        bill_to_data = raw_data.get("bill_to", {})
        bill_to = None
        if bill_to_data:
            bill_to = BillTo(
                company=bill_to_data.get("company"),
                address=bill_to_data.get("address"),
            )
        
        return ExtractedInvoiceData(
            invoice_number=raw_data.get("invoice_number", "UNKNOWN"),
            invoice_date=raw_data.get("invoice_date", ""),
            supplier_name=raw_data.get("supplier_name", "Unknown Supplier"),
            supplier_address=raw_data.get("supplier_address"),
            supplier_vat=raw_data.get("supplier_vat"),
            po_reference=raw_data.get("po_reference"),
            payment_terms=raw_data.get("payment_terms"),
            bill_to=bill_to,
            line_items=line_items,
            subtotal=self._parse_float(raw_data.get("subtotal", 0)),
            vat_rate=self._parse_float(raw_data.get("vat_rate")) if raw_data.get("vat_rate") else None,
            vat_amount=self._parse_float(raw_data.get("vat_amount")) if raw_data.get("vat_amount") else None,
            total=self._parse_float(raw_data.get("total", 0)),
            currency=raw_data.get("currency", "GBP"),
        )
    
    def _assess_quality(self, raw_data: dict, pdf_info: dict) -> DocumentQuality:
        
        confidence_str = (raw_data.get("confidence_assessment") or "medium").lower()
        notes = (raw_data.get("extraction_notes") or "").lower()
        
        poor_indicators = ["blur", "rotated", "unclear", "difficult", "scan", "poor"]
        has_poor_quality = any(ind in notes for ind in poor_indicators)
        
        if confidence_str == "high" and not has_poor_quality:
            return DocumentQuality.EXCELLENT
        elif confidence_str == "high" or (confidence_str == "medium" and not has_poor_quality):
            return DocumentQuality.GOOD
        elif confidence_str == "medium":
            return DocumentQuality.ACCEPTABLE
        else:
            return DocumentQuality.POOR
    
    def _calculate_confidence(self, raw_data: dict, extracted: ExtractedInvoiceData) -> float:
        
        base_confidence = 0.85
        
        model_assessment = (raw_data.get("confidence_assessment") or "medium").lower()
        if model_assessment == "high":
            base_confidence = 0.95
        elif model_assessment == "medium":
            base_confidence = 0.85
        else:
            base_confidence = 0.70
        
        if not extracted.invoice_number or extracted.invoice_number == "UNKNOWN":
            base_confidence -= 0.10
        if not extracted.supplier_name or extracted.supplier_name == "Unknown Supplier":
            base_confidence -= 0.10
        if not extracted.line_items:
            base_confidence -= 0.20
        if extracted.total == 0:
            base_confidence -= 0.15
        
        if extracted.po_reference:
            base_confidence = min(base_confidence + 0.02, 0.99)
        
        return max(0.30, min(base_confidence, 0.99))
    
    def _build_field_confidences(self, raw_data: dict, extracted: ExtractedInvoiceData) -> dict:
        
        base = 0.95 if raw_data.get("confidence_assessment") == "high" else 0.85
        
        confidences = {
            "invoice_number": base if extracted.invoice_number != "UNKNOWN" else 0.50,
            "invoice_date": base if extracted.invoice_date else 0.50,
            "supplier_name": base if extracted.supplier_name != "Unknown Supplier" else 0.50,
            "po_reference": base if extracted.po_reference else 0.0,
            "line_items": base if extracted.line_items else 0.30,
            "total": base if extracted.total > 0 else 0.50,
        }
        
        return confidences
    
    def _build_reasoning(
        self, 
        raw_data: dict, 
        extracted: ExtractedInvoiceData,
        quality: DocumentQuality,
        confidence: float
    ) -> str:
        
        notes = raw_data.get("extraction_notes", "No extraction notes")
        
        reasoning = (
            f"Document processed with {quality.value} quality assessment. "
            f"Extracted invoice {extracted.invoice_number} from {extracted.supplier_name}. "
            f"Found {len(extracted.line_items)} line items totaling {extracted.currency} {extracted.total:.2f}. "
        )
        
        if extracted.po_reference:
            reasoning += f"PO reference found: {extracted.po_reference}. "
        else:
            reasoning += "No PO reference found on invoice - will require fuzzy matching. "
        
        reasoning += f"Extraction notes: {notes}. Overall confidence: {confidence*100:.1f}%."
        
        return reasoning
    
    def _collect_warnings(self, raw_data: dict, extracted: ExtractedInvoiceData) -> list:
        
        warnings = []
        
        if not extracted.po_reference:
            warnings.append("Missing PO reference - fuzzy matching required")
        
        if not extracted.invoice_date:
            warnings.append("Could not extract invoice date")
        
        if extracted.total == 0:
            warnings.append("Invoice total is zero - likely extraction error")
        
        if not extracted.line_items:
            warnings.append("No line items extracted - document may be unreadable")
        
        notes = raw_data.get("extraction_notes") or ""
        if "unclear" in notes.lower() or "difficult" in notes.lower():
            warnings.append(f"Extraction difficulty noted: {notes}")
        
        return warnings
