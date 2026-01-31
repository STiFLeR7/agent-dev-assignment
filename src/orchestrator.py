import json
from typing import Dict, Any, List, TypedDict, Annotated, Optional
from datetime import datetime
from pathlib import Path
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .agents import (
    DocumentIntelligenceAgent,
    MatchingAgent,
    DiscrepancyDetectionAgent,
    ResolutionRecommendationAgent,
)
from .models import (
    PurchaseOrder,
    POLineItem,
    ExtractionResult,
    MatchingResult,
    DiscrepancyResult,
    ResolutionResult,
    AgentExecutionTrace,
    InvoiceProcessingOutput,
    ProcessingResults,
    DocumentInfo,
    DocumentQuality,
)
from .config import PO_DATABASE_FILE

class WorkflowState(TypedDict):
    
    invoice_path: str
    po_database: List[Dict[str, Any]]
    
    extraction_result: Optional[Dict[str, Any]]
    matching_result: Optional[Dict[str, Any]]
    discrepancy_result: Optional[Dict[str, Any]]
    resolution_result: Optional[Dict[str, Any]]
    
    start_time: str
    agent_traces: Dict[str, Dict[str, Any]]
    errors: List[str]
    current_agent: str

class InvoiceReconciliationWorkflow:
    
    
    def __init__(self, api_key: Optional[str] = None):
        
        self.doc_intel_agent = DocumentIntelligenceAgent(api_key=api_key)
        self.matching_agent = MatchingAgent()
        self.discrepancy_agent = DiscrepancyDetectionAgent()
        self.resolution_agent = ResolutionRecommendationAgent()
        
        self.po_database = self._load_po_database()
        
        self.graph = self._build_graph()
        self.app = self.graph.compile()
    
    def _load_po_database(self) -> List[PurchaseOrder]:
        
        with open(PO_DATABASE_FILE, 'r') as f:
            data = json.load(f)
        
        pos = []
        for po_data in data.get("purchase_orders", []):
            line_items = [
                POLineItem(**item) for item in po_data.get("line_items", [])
            ]
            pos.append(PurchaseOrder(
                po_number=po_data["po_number"],
                supplier=po_data["supplier"],
                date=po_data["date"],
                total=po_data["total"],
                currency=po_data["currency"],
                line_items=line_items,
            ))
        
        return pos
    
    def _build_graph(self) -> StateGraph:
        
        workflow = StateGraph(WorkflowState)
        
        workflow.add_node("document_intelligence", self._run_document_intelligence)
        workflow.add_node("matching", self._run_matching)
        workflow.add_node("discrepancy_detection", self._run_discrepancy_detection)
        workflow.add_node("resolution", self._run_resolution)
        workflow.add_node("error_handler", self._handle_error)
        
        workflow.set_entry_point("document_intelligence")
        
        workflow.add_conditional_edges(
            "document_intelligence",
            self._route_after_extraction,
            {
                "continue": "matching",
                "error": "error_handler",
            }
        )
        
        workflow.add_conditional_edges(
            "matching",
            self._route_after_matching,
            {
                "continue": "discrepancy_detection",
                "no_match": "resolution",
                "error": "error_handler",
            }
        )
        
        workflow.add_edge("discrepancy_detection", "resolution")
        
        workflow.add_edge("resolution", END)
        workflow.add_edge("error_handler", END)
        
        return workflow
    
    def _run_document_intelligence(self, state: WorkflowState) -> WorkflowState:
        
        start_time = datetime.now()
        state["current_agent"] = "document_intelligence"
        
        try:
            result = self.doc_intel_agent.process(state["invoice_path"])
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            state["extraction_result"] = result.model_dump()
            state["agent_traces"]["document_intelligence"] = {
                "duration_ms": duration_ms,
                "confidence": result.extraction_confidence,
                "status": "success",
                "errors": [],
            }
            
            print(f"  ✓ Document Intelligence: Extracted invoice {result.extracted_data.invoice_number}")
            print(f"    Confidence: {result.extraction_confidence*100:.1f}%, Quality: {result.document_quality.value}")
            
        except Exception as e:
            state["errors"].append(f"Document Intelligence Error: {str(e)}")
            state["agent_traces"]["document_intelligence"] = {
                "duration_ms": int((datetime.now() - start_time).total_seconds() * 1000),
                "confidence": 0.0,
                "status": "error",
                "errors": [str(e)],
            }
            print(f"  ✗ Document Intelligence Error: {e}")
        
        return state
    
    def _run_matching(self, state: WorkflowState) -> WorkflowState:
        
        start_time = datetime.now()
        state["current_agent"] = "matching"
        
        try:
            extraction_result = ExtractionResult(**state["extraction_result"])
            
            po_models = self.po_database
            
            result = self.matching_agent.process(extraction_result, po_models)
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            state["matching_result"] = result.model_dump()
            state["agent_traces"]["matching"] = {
                "duration_ms": duration_ms,
                "confidence": result.po_match_confidence,
                "status": "success",
                "errors": [],
            }
            
            if result.matched_po:
                print(f"  ✓ Matching: Found PO {result.matched_po}")
                print(f"    Method: {result.match_method.value}, Confidence: {result.po_match_confidence*100:.1f}%")
            else:
                print(f"  ⚠ Matching: No PO match found (confidence: {result.po_match_confidence*100:.1f}%)")
            
        except Exception as e:
            state["errors"].append(f"Matching Error: {str(e)}")
            state["agent_traces"]["matching"] = {
                "duration_ms": int((datetime.now() - start_time).total_seconds() * 1000),
                "confidence": 0.0,
                "status": "error",
                "errors": [str(e)],
            }
            print(f"  ✗ Matching Error: {e}")
        
        return state
    
    def _run_discrepancy_detection(self, state: WorkflowState) -> WorkflowState:
        
        start_time = datetime.now()
        state["current_agent"] = "discrepancy_detection"
        
        try:
            extraction_result = ExtractionResult(**state["extraction_result"])
            matching_result = MatchingResult(**state["matching_result"])
            
            result = self.discrepancy_agent.process(extraction_result, matching_result)
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            state["discrepancy_result"] = result.model_dump()
            state["agent_traces"]["discrepancy_detection"] = {
                "duration_ms": duration_ms,
                "confidence": 0.99 if result.discrepancies_found == 0 else 0.95,
                "status": "success",
                "errors": [],
            }
            
            if result.discrepancies_found == 0:
                print(f"  ✓ Discrepancy Detection: No discrepancies found")
            else:
                print(f"  ⚠ Discrepancy Detection: Found {result.discrepancies_found} discrepancy(ies)")
                for disc in result.discrepancies[:3]:
                    print(f"    - {disc.type.value}: {disc.severity.value} severity")
            
        except Exception as e:
            state["errors"].append(f"Discrepancy Detection Error: {str(e)}")
            state["agent_traces"]["discrepancy_detection"] = {
                "duration_ms": int((datetime.now() - start_time).total_seconds() * 1000),
                "confidence": 0.0,
                "status": "error",
                "errors": [str(e)],
            }
            print(f"  ✗ Discrepancy Detection Error: {e}")
        
        return state
    
    def _run_resolution(self, state: WorkflowState) -> WorkflowState:
        
        start_time = datetime.now()
        state["current_agent"] = "resolution"
        
        try:
            extraction_result = ExtractionResult(**state["extraction_result"])
            
            if state.get("matching_result"):
                matching_result = MatchingResult(**state["matching_result"])
            else:
                from .models import MatchMethod
                matching_result = MatchingResult(
                    po_match_confidence=0.0,
                    matched_po=None,
                    matched_po_data=None,
                    match_method=MatchMethod.NO_MATCH,
                    supplier_match=False,
                    date_variance_days=None,
                    line_items_matched=0,
                    line_items_total=len(extraction_result.extracted_data.line_items),
                    match_rate=0.0,
                    alternative_matches=[],
                    agent_reasoning="No matching performed due to earlier errors.",
                )
            
            if state.get("discrepancy_result"):
                discrepancy_result = DiscrepancyResult(**state["discrepancy_result"])
            else:
                from .models import TotalVariance
                discrepancy_result = DiscrepancyResult(
                    discrepancies_found=1,
                    discrepancies=[],
                    price_variances=[],
                    quantity_variances=[],
                    total_variance=TotalVariance(amount=0, percentage=0, within_tolerance=False),
                    agent_reasoning="No discrepancy analysis performed due to missing PO match.",
                )
            
            result = self.resolution_agent.process(
                extraction_result, matching_result, discrepancy_result
            )
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            state["resolution_result"] = result.model_dump()
            state["agent_traces"]["resolution"] = {
                "duration_ms": duration_ms,
                "confidence": result.confidence,
                "status": "success",
                "errors": [],
            }
            
            action_emoji = {
                "auto_approve": "✅",
                "flag_for_review": "🔶",
                "escalate_to_human": "🔴",
            }
            emoji = action_emoji.get(result.recommended_action.value, "❓")
            print(f"  {emoji} Resolution: {result.recommended_action.value.upper()}")
            print(f"    Risk: {result.risk_level.value}, Confidence: {result.confidence*100:.1f}%")
            
        except Exception as e:
            state["errors"].append(f"Resolution Error: {str(e)}")
            state["agent_traces"]["resolution"] = {
                "duration_ms": int((datetime.now() - start_time).total_seconds() * 1000),
                "confidence": 0.0,
                "status": "error",
                "errors": [str(e)],
            }
            print(f"  ✗ Resolution Error: {e}")
        
        return state
    
    def _handle_error(self, state: WorkflowState) -> WorkflowState:
        
        print(f"  ⚠ Error handler invoked. Errors: {state['errors']}")
        
        from .models import RecommendedAction, RiskLevel
        state["resolution_result"] = {
            "recommended_action": RecommendedAction.ESCALATE_TO_HUMAN.value,
            "confidence": 0.50,
            "risk_level": RiskLevel.HIGH.value,
            "approval_criteria_met": [],
            "approval_criteria_failed": ["processing_error"],
            "human_review_required": True,
            "reasoning": f"Processing failed with errors: {'; '.join(state['errors'])}. Manual review required.",
        }
        
        return state
    
    def _route_after_extraction(self, state: WorkflowState) -> str:
        
        if state.get("extraction_result") and not state.get("errors"):
            return "continue"
        return "error"
    
    def _route_after_matching(self, state: WorkflowState) -> str:
        
        if state.get("errors"):
            return "error"
        
        if state.get("matching_result"):
            matching = state["matching_result"]
            return "continue"
        
        return "no_match"
    
    def process_invoice(self, invoice_path: str) -> InvoiceProcessingOutput:
        
        print(f"\n{'='*60}")
        print(f"Processing: {Path(invoice_path).name}")
        print(f"{'='*60}")
        
        start_time = datetime.now()
        
        initial_state: WorkflowState = {
            "invoice_path": str(invoice_path),
            "po_database": [po.model_dump() for po in self.po_database],
            "extraction_result": None,
            "matching_result": None,
            "discrepancy_result": None,
            "resolution_result": None,
            "start_time": start_time.isoformat(),
            "agent_traces": {},
            "errors": [],
            "current_agent": "",
        }
        
        final_state = self.app.invoke(initial_state)
        
        duration_seconds = (datetime.now() - start_time).total_seconds()
        
        output = self._build_output(final_state, invoice_path, duration_seconds)
        
        print(f"\n{'─'*60}")
        print(f"Completed in {duration_seconds:.2f}s")
        print(f"Final recommendation: {output.processing_results.recommended_action.value}")
        print(f"{'='*60}\n")
        
        return output
    
    def _build_output(
        self, 
        state: WorkflowState, 
        invoice_path: str,
        duration_seconds: float
    ) -> InvoiceProcessingOutput:
        
        from .utils.pdf_utils import get_pdf_info
        from .models import RecommendedAction, RiskLevel, TotalVariance, ExtractedInvoiceData
        
        pdf_info = get_pdf_info(invoice_path)
        
        extraction = None
        if state.get("extraction_result"):
            try:
                extraction = ExtractionResult(**state["extraction_result"])
            except Exception as e:
                print(f"Warning: Could not parse extraction result: {e}")
        
        matching = None
        if state.get("matching_result"):
            try:
                matching = MatchingResult(**state["matching_result"])
            except Exception as e:
                print(f"Warning: Could not parse matching result: {e}")
        
        discrepancy = None
        if state.get("discrepancy_result"):
            try:
                discrepancy = DiscrepancyResult(**state["discrepancy_result"])
            except Exception as e:
                print(f"Warning: Could not parse discrepancy result: {e}")
        
        resolution = None
        if state.get("resolution_result"):
            try:
                resolution = ResolutionResult(**state["resolution_result"])
            except Exception as e:
                print(f"Warning: Could not parse resolution result: {e}")
        
        doc_info = DocumentInfo(
            filename=pdf_info["filename"],
            file_size_kb=pdf_info["file_size_kb"],
            page_count=pdf_info["page_count"],
            document_quality=extraction.document_quality if extraction else DocumentQuality.POOR,
        )
        
        default_total_variance = TotalVariance(amount=0, percentage=0, within_tolerance=False)
        
        processing_results = ProcessingResults(
            extraction_confidence=extraction.extraction_confidence if extraction else 0.0,
            document_quality=extraction.document_quality if extraction else DocumentQuality.POOR,
            extracted_data=extraction.extracted_data if extraction else None,
            matching_results=matching,
            discrepancies=discrepancy.discrepancies if discrepancy else [],
            total_variance=discrepancy.total_variance if discrepancy else default_total_variance,
            recommended_action=resolution.recommended_action if resolution else RecommendedAction.ESCALATE_TO_HUMAN,
            risk_level=resolution.risk_level if resolution else RiskLevel.HIGH,
            confidence=resolution.confidence if resolution else 0.0,
            agent_reasoning=resolution.reasoning if resolution else f"Processing failed. Errors: {'; '.join(state.get('errors', []))}",
        )
        
        traces = {}
        for agent_name, trace_data in state.get("agent_traces", {}).items():
            traces[agent_name] = AgentExecutionTrace(**trace_data)
        
        return InvoiceProcessingOutput(
            invoice_id=extraction.extracted_data.invoice_number if extraction else "UNKNOWN",
            processing_timestamp=datetime.now().isoformat() + "Z",
            processing_duration_seconds=duration_seconds,
            document_info=doc_info,
            processing_results=processing_results,
            agent_execution_trace=traces,
        )
    
    def process_all_invoices(self, invoice_paths: List[str]) -> List[InvoiceProcessingOutput]:
        
        results = []
        total_start = datetime.now()
        
        print(f"\n{'#'*60}")
        print(f"INVOICE RECONCILIATION MULTI-AGENT SYSTEM")
        print(f"Processing {len(invoice_paths)} invoice(s)")
        print(f"{'#'*60}")
        
        for path in invoice_paths:
            result = self.process_invoice(path)
            results.append(result)
        
        total_duration = (datetime.now() - total_start).total_seconds()
        
        print(f"\n{'#'*60}")
        print(f"PROCESSING SUMMARY")
        print(f"{'#'*60}")
        print(f"Total invoices: {len(results)}")
        print(f"Total time: {total_duration:.2f}s")
        
        actions = {}
        for r in results:
            action = r.processing_results.recommended_action.value
            actions[action] = actions.get(action, 0) + 1
        
        for action, count in actions.items():
            print(f"  {action}: {count}")
        
        return results
