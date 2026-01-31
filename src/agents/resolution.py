from typing import List, Optional
from datetime import datetime

from ..models import (
    ResolutionResult,
    RecommendedAction,
    RiskLevel,
    ExtractionResult,
    MatchingResult,
    DiscrepancyResult,
    Discrepancy,
    Severity,
    DiscrepancyType,
)
from ..config import ReconciliationThresholds

class ResolutionRecommendationAgent:
    
    
    def __init__(self):
        
        self.name = "Resolution Recommendation Agent"
        self.thresholds = ReconciliationThresholds()
    
    def process(
        self,
        extraction_result: ExtractionResult,
        matching_result: MatchingResult,
        discrepancy_result: DiscrepancyResult
    ) -> ResolutionResult:
        
        criteria_met = []
        criteria_failed = []
        
        extraction_ok = extraction_result.extraction_confidence >= self.thresholds.MIN_EXTRACTION_CONFIDENCE
        if extraction_ok:
            criteria_met.append("high_extraction_confidence")
        else:
            criteria_failed.append("low_extraction_confidence")
        
        po_matched = matching_result.matched_po is not None
        exact_po_match = matching_result.po_match_confidence >= 0.95
        
        if exact_po_match:
            criteria_met.append("exact_po_match")
        elif po_matched:
            criteria_met.append("fuzzy_po_match")
        else:
            criteria_failed.append("no_po_match")
        
        if matching_result.supplier_match:
            criteria_met.append("verified_supplier")
        else:
            criteria_failed.append("supplier_mismatch")
        
        all_items_match = matching_result.match_rate >= 1.0
        if all_items_match:
            criteria_met.append("all_items_match")
        elif matching_result.match_rate >= 0.8:
            criteria_met.append("most_items_match")
        else:
            criteria_failed.append("items_mismatch")
        
        no_discrepancies = discrepancy_result.discrepancies_found == 0
        if no_discrepancies:
            criteria_met.append("zero_discrepancies")
        else:
            criteria_failed.append(f"{discrepancy_result.discrepancies_found}_discrepancies")
        
        if discrepancy_result.total_variance.within_tolerance:
            criteria_met.append("total_within_tolerance")
        else:
            criteria_failed.append("total_outside_tolerance")
        
        action, risk_level, confidence = self._determine_action(
            extraction_result,
            matching_result,
            discrepancy_result,
            criteria_met,
            criteria_failed,
        )
        
        human_review_required = action != RecommendedAction.AUTO_APPROVE
        
        reasoning = self._build_reasoning(
            action,
            risk_level,
            confidence,
            extraction_result,
            matching_result,
            discrepancy_result,
            criteria_met,
            criteria_failed,
        )
        
        return ResolutionResult(
            recommended_action=action,
            confidence=confidence,
            risk_level=risk_level,
            approval_criteria_met=criteria_met,
            approval_criteria_failed=criteria_failed,
            human_review_required=human_review_required,
            reasoning=reasoning,
        )
    
    def _determine_action(
        self,
        extraction_result: ExtractionResult,
        matching_result: MatchingResult,
        discrepancy_result: DiscrepancyResult,
        criteria_met: List[str],
        criteria_failed: List[str],
    ) -> tuple:
        
        discrepancies = discrepancy_result.discrepancies
        
        escalation_reasons = []
        
        critical_price_disc = [
            d for d in discrepancies 
            if d.type == DiscrepancyType.PRICE_MISMATCH 
            and d.variance_percentage is not None
            and abs(d.variance_percentage) > self.thresholds.PRICE_VARIANCE_ESCALATE
        ]
        if critical_price_disc:
            escalation_reasons.append("significant_price_variance")
        
        if matching_result.po_match_confidence < self.thresholds.NO_MATCH_CONFIDENCE:
            escalation_reasons.append("no_matching_po")
        
        if abs(discrepancy_result.total_variance.percentage) > self.thresholds.TOTAL_VARIANCE_ESCALATE:
            escalation_reasons.append("large_total_variance")
        
        if discrepancy_result.discrepancies_found >= self.thresholds.MAX_DISCREPANCIES_BEFORE_ESCALATE:
            escalation_reasons.append("multiple_discrepancies")
        
        if extraction_result.extraction_confidence < self.thresholds.VERY_LOW_CONFIDENCE:
            escalation_reasons.append("very_low_extraction_confidence")
        
        if escalation_reasons:
            return (
                RecommendedAction.ESCALATE_TO_HUMAN,
                RiskLevel.HIGH if len(escalation_reasons) > 1 else RiskLevel.MEDIUM,
                0.90,
            )
        
        review_reasons = []
        
        moderate_price_disc = [
            d for d in discrepancies
            if d.type == DiscrepancyType.PRICE_MISMATCH
            and d.variance_percentage is not None
            and self.thresholds.PRICE_VARIANCE_REVIEW_MIN < abs(d.variance_percentage) <= self.thresholds.PRICE_VARIANCE_REVIEW_MAX
        ]
        if moderate_price_disc:
            review_reasons.append("moderate_price_variance")
        
        qty_mismatches = [d for d in discrepancies if d.type == DiscrepancyType.QUANTITY_MISMATCH]
        if qty_mismatches:
            review_reasons.append("quantity_mismatch")
        
        missing_po = [d for d in discrepancies if d.type == DiscrepancyType.MISSING_PO_REFERENCE]
        if missing_po and matching_result.po_match_confidence >= self.thresholds.FUZZY_MATCH_MIN_CONFIDENCE:
            review_reasons.append("missing_po_fuzzy_match")
        
        if (self.thresholds.LOW_EXTRACTION_CONFIDENCE_MIN <= 
            extraction_result.extraction_confidence < 
            self.thresholds.LOW_EXTRACTION_CONFIDENCE_MAX):
            review_reasons.append("low_extraction_confidence")
        
        if matching_result.match_rate < 1.0 and matching_result.match_rate >= 0.7:
            review_reasons.append("partial_match")
        
        if not matching_result.supplier_match:
            review_reasons.append("supplier_mismatch")
        
        if review_reasons:
            return (
                RecommendedAction.FLAG_FOR_REVIEW,
                RiskLevel.MEDIUM if len(review_reasons) > 2 else RiskLevel.LOW,
                0.85,
            )
        
        if (extraction_result.extraction_confidence >= self.thresholds.MIN_EXTRACTION_CONFIDENCE
            and matching_result.po_match_confidence >= 0.90
            and discrepancy_result.discrepancies_found == 0
            and discrepancy_result.total_variance.within_tolerance):
            return (
                RecommendedAction.AUTO_APPROVE,
                RiskLevel.NONE,
                0.98,
            )
        
        return (
            RecommendedAction.FLAG_FOR_REVIEW,
            RiskLevel.LOW,
            0.75,
        )
    
    def _build_reasoning(
        self,
        action: RecommendedAction,
        risk_level: RiskLevel,
        confidence: float,
        extraction_result: ExtractionResult,
        matching_result: MatchingResult,
        discrepancy_result: DiscrepancyResult,
        criteria_met: List[str],
        criteria_failed: List[str],
    ) -> str:
        
        extracted = extraction_result.extracted_data
        
        parts = [
            f"Invoice {extracted.invoice_number} processed."
        ]
        
        parts.append(
            f"Extraction confidence: {extraction_result.extraction_confidence*100:.0f}% "
            f"({extraction_result.document_quality.value} quality)."
        )
        
        if matching_result.matched_po:
            parts.append(
                f"Matched to PO {matching_result.matched_po} "
                f"({matching_result.po_match_confidence*100:.0f}% confidence, "
                f"{matching_result.match_method.value})."
            )
        else:
            parts.append("Could not match to any PO with sufficient confidence.")
        
        if discrepancy_result.discrepancies_found == 0:
            parts.append("No discrepancies detected.")
        else:
            parts.append(f"{discrepancy_result.discrepancies_found} discrepancy(ies) found.")
            
            for disc in discrepancy_result.discrepancies:
                if disc.severity in [Severity.CRITICAL, Severity.HIGH]:
                    parts.append(f"⚠️ {disc.type.value}: {disc.details}")
        
        tv = discrepancy_result.total_variance
        parts.append(
            f"Total variance: £{tv.amount:.2f} ({tv.percentage:.1f}%) - "
            f"{'within' if tv.within_tolerance else 'outside'} tolerance."
        )
        
        if action == RecommendedAction.AUTO_APPROVE:
            parts.append(
                f"✅ RECOMMENDATION: Auto-approve. "
                f"All criteria met: {', '.join(criteria_met)}. "
                f"Risk level: {risk_level.value}. Confidence: {confidence*100:.0f}%."
            )
        elif action == RecommendedAction.FLAG_FOR_REVIEW:
            parts.append(
                f"🔶 RECOMMENDATION: Flag for review. "
                f"Issues: {', '.join(criteria_failed)}. "
                f"Risk level: {risk_level.value}. Confidence: {confidence*100:.0f}%."
            )
        else:
            parts.append(
                f"🔴 RECOMMENDATION: Escalate to human. "
                f"Critical issues: {', '.join(criteria_failed)}. "
                f"Risk level: {risk_level.value}. Confidence: {confidence*100:.0f}%."
            )
        
        return " ".join(parts)
