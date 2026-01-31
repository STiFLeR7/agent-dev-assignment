from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class RecommendedAction(str, Enum):
    
    AUTO_APPROVE = "auto_approve"
    FLAG_FOR_REVIEW = "flag_for_review"
    ESCALATE_TO_HUMAN = "escalate_to_human"

class RiskLevel(str, Enum):
    
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class DiscrepancyType(str, Enum):
    
    PRICE_MISMATCH = "price_mismatch"
    QUANTITY_MISMATCH = "quantity_mismatch"
    MISSING_PO_REFERENCE = "missing_po_reference"
    SUPPLIER_MISMATCH = "supplier_mismatch"
    ITEM_NOT_FOUND = "item_not_found"
    TOTAL_VARIANCE = "total_variance"
    DATE_VARIANCE = "date_variance"
    PARTIAL_MATCH = "partial_match"

class Severity(str, Enum):
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class MatchMethod(str, Enum):
    
    EXACT_PO_REFERENCE = "exact_po_reference"
    SUPPLIER_DATE_PRODUCT = "supplier_date_product"
    PRODUCT_ONLY_FUZZY = "product_only_fuzzy"
    NO_MATCH = "no_match"

class DocumentQuality(str, Enum):
    
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"

class ExtractedLineItem(BaseModel):
    
    item_code: Optional[str] = None
    description: str
    quantity: float
    unit: str = "units"
    unit_price: float
    line_total: float
    extraction_confidence: float = Field(ge=0.0, le=1.0, default=0.95)

class POLineItem(BaseModel):
    
    item_id: str
    description: str
    quantity: float
    unit: str
    unit_price: float
    line_total: float

class BillTo(BaseModel):
    
    company: Optional[str] = None
    address: Optional[str] = None

class ExtractedInvoiceData(BaseModel):
    
    invoice_number: str
    invoice_date: str
    supplier_name: str
    supplier_address: Optional[str] = None
    supplier_vat: Optional[str] = None
    po_reference: Optional[str] = None
    payment_terms: Optional[str] = None
    bill_to: Optional[BillTo] = None
    line_items: List[ExtractedLineItem]
    subtotal: float
    vat_rate: Optional[float] = None
    vat_amount: Optional[float] = None
    total: float
    currency: str = "GBP"

class ExtractionResult(BaseModel):
    
    extracted_data: ExtractedInvoiceData
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    document_quality: DocumentQuality
    field_confidences: Dict[str, float] = Field(default_factory=dict)
    agent_reasoning: str
    warnings: List[str] = Field(default_factory=list)

class PurchaseOrder(BaseModel):
    
    po_number: str
    supplier: str
    date: str
    total: float
    currency: str
    line_items: List[POLineItem]

class AlternativeMatch(BaseModel):
    
    po_number: str
    confidence: float
    match_method: MatchMethod
    reasoning: str

class MatchingResult(BaseModel):
    
    po_match_confidence: float = Field(ge=0.0, le=1.0)
    matched_po: Optional[str] = None
    matched_po_data: Optional[PurchaseOrder] = None
    match_method: MatchMethod
    supplier_match: bool
    date_variance_days: Optional[int] = None
    line_items_matched: int
    line_items_total: int
    match_rate: float = Field(ge=0.0, le=1.0)
    alternative_matches: List[AlternativeMatch] = Field(default_factory=list)
    agent_reasoning: str

class Discrepancy(BaseModel):
    
    type: DiscrepancyType
    severity: Severity
    line_item_index: Optional[int] = None
    field: str
    invoice_value: Any
    po_value: Any
    variance_percentage: Optional[float] = None
    details: str
    recommended_action: RecommendedAction
    confidence: float = Field(ge=0.0, le=1.0)

class TotalVariance(BaseModel):
    
    amount: float
    percentage: float
    within_tolerance: bool

class DiscrepancyResult(BaseModel):
    
    discrepancies_found: int
    discrepancies: List[Discrepancy]
    price_variances: List[Dict[str, Any]] = Field(default_factory=list)
    quantity_variances: List[Dict[str, Any]] = Field(default_factory=list)
    total_variance: TotalVariance
    agent_reasoning: str

class ResolutionResult(BaseModel):
    
    recommended_action: RecommendedAction
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    approval_criteria_met: List[str] = Field(default_factory=list)
    approval_criteria_failed: List[str] = Field(default_factory=list)
    human_review_required: bool
    reasoning: str

class AgentExecutionTrace(BaseModel):
    
    duration_ms: int
    confidence: float
    status: str
    errors: List[str] = Field(default_factory=list)

class DocumentInfo(BaseModel):
    
    filename: str
    file_size_kb: float
    page_count: int = 1
    document_quality: DocumentQuality

class ProcessingResults(BaseModel):
    
    extraction_confidence: float
    document_quality: DocumentQuality
    extracted_data: Optional[ExtractedInvoiceData] = None
    matching_results: Optional[MatchingResult] = None
    discrepancies: List[Discrepancy] = Field(default_factory=list)
    total_variance: Optional[TotalVariance] = None
    recommended_action: Optional[RecommendedAction] = None
    risk_level: Optional[RiskLevel] = None
    confidence: float = 0.0
    agent_reasoning: str = ""

class InvoiceProcessingOutput(BaseModel):
    
    invoice_id: str
    processing_timestamp: str
    processing_duration_seconds: float
    document_info: DocumentInfo
    processing_results: ProcessingResults
    agent_execution_trace: Dict[str, AgentExecutionTrace]

class AgentState(BaseModel):
    
    invoice_path: str
    po_database: List[PurchaseOrder]
    
    extraction_result: Optional[ExtractionResult] = None
    matching_result: Optional[MatchingResult] = None
    discrepancy_result: Optional[DiscrepancyResult] = None
    resolution_result: Optional[ResolutionResult] = None
    
    start_time: Optional[datetime] = None
    agent_traces: Dict[str, AgentExecutionTrace] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True
