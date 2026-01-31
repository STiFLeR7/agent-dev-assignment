from typing import List, Optional, Dict, Any
from datetime import datetime

from ..models import (
    DiscrepancyResult,
    Discrepancy,
    DiscrepancyType,
    Severity,
    TotalVariance,
    RecommendedAction,
    ExtractionResult,
    MatchingResult,
    ExtractedLineItem,
    POLineItem,
)
from ..utils.matching_utils import fuzzy_match_product
from ..config import ReconciliationThresholds

class DiscrepancyDetectionAgent:
    
    
    def __init__(self):
        
        self.name = "Discrepancy Detection Agent"
        self.thresholds = ReconciliationThresholds()
    
    def process(
        self,
        extraction_result: ExtractionResult,
        matching_result: MatchingResult
    ) -> DiscrepancyResult:
        
        discrepancies = []
        price_variances = []
        quantity_variances = []
        
        extracted = extraction_result.extracted_data
        
        if not matching_result.matched_po_data:
            discrepancies.append(Discrepancy(
                type=DiscrepancyType.MISSING_PO_REFERENCE,
                severity=Severity.HIGH,
                field="po_reference",
                invoice_value=extracted.po_reference,
                po_value=None,
                details=(
                    f"Invoice has {'invalid PO reference: ' + extracted.po_reference if extracted.po_reference else 'no PO reference'}. "
                    f"Could not find matching PO in database with sufficient confidence."
                ),
                recommended_action=RecommendedAction.ESCALATE_TO_HUMAN,
                confidence=0.95,
            ))
            
            return DiscrepancyResult(
                discrepancies_found=len(discrepancies),
                discrepancies=discrepancies,
                price_variances=price_variances,
                quantity_variances=quantity_variances,
                total_variance=TotalVariance(amount=0, percentage=0, within_tolerance=False),
                agent_reasoning="Cannot perform detailed discrepancy analysis without matched PO. Invoice should be escalated for manual matching.",
            )
        
        po = matching_result.matched_po_data
        
        if not extracted.po_reference:
            discrepancies.append(Discrepancy(
                type=DiscrepancyType.MISSING_PO_REFERENCE,
                severity=Severity.MEDIUM,
                field="po_reference",
                invoice_value=None,
                po_value=po.po_number,
                details=(
                    f"Invoice does not contain a PO reference. "
                    f"Fuzzy matching suggests PO-{po.po_number} "
                    f"({matching_result.po_match_confidence*100:.0f}% confidence)."
                ),
                recommended_action=RecommendedAction.FLAG_FOR_REVIEW,
                confidence=matching_result.po_match_confidence,
            ))
        
        if not matching_result.supplier_match:
            discrepancies.append(Discrepancy(
                type=DiscrepancyType.SUPPLIER_MISMATCH,
                severity=Severity.MEDIUM,
                field="supplier_name",
                invoice_value=extracted.supplier_name,
                po_value=po.supplier,
                details=f"Supplier name mismatch: Invoice shows '{extracted.supplier_name}', PO shows '{po.supplier}'.",
                recommended_action=RecommendedAction.FLAG_FOR_REVIEW,
                confidence=0.90,
            ))
        
        line_discrepancies = self._compare_line_items(extracted.line_items, po.line_items)
        
        for disc in line_discrepancies:
            discrepancies.append(disc)
            
            if disc.type == DiscrepancyType.PRICE_MISMATCH:
                price_variances.append({
                    "line_item": disc.line_item_index,
                    "invoice_price": disc.invoice_value,
                    "po_price": disc.po_value,
                    "variance_percent": disc.variance_percentage,
                })
            elif disc.type == DiscrepancyType.QUANTITY_MISMATCH:
                quantity_variances.append({
                    "line_item": disc.line_item_index,
                    "invoice_qty": disc.invoice_value,
                    "po_qty": disc.po_value,
                    "variance_percent": disc.variance_percentage,
                })
        
        total_variance = self._calculate_total_variance(extracted.total, po.total)
        
        if not total_variance.within_tolerance:
            severity = Severity.HIGH if abs(total_variance.percentage) > 10 else Severity.MEDIUM
            discrepancies.append(Discrepancy(
                type=DiscrepancyType.TOTAL_VARIANCE,
                severity=severity,
                field="total",
                invoice_value=extracted.total,
                po_value=po.total,
                variance_percentage=total_variance.percentage,
                details=(
                    f"Invoice total £{extracted.total:.2f} differs from PO total £{po.total:.2f} "
                    f"by £{total_variance.amount:.2f} ({total_variance.percentage:.1f}%)."
                ),
                recommended_action=(
                    RecommendedAction.ESCALATE_TO_HUMAN if severity == Severity.HIGH 
                    else RecommendedAction.FLAG_FOR_REVIEW
                ),
                confidence=0.99,
            ))
        
        if matching_result.line_items_matched < matching_result.line_items_total:
            unmatched_count = matching_result.line_items_total - matching_result.line_items_matched
            discrepancies.append(Discrepancy(
                type=DiscrepancyType.PARTIAL_MATCH,
                severity=Severity.MEDIUM,
                field="line_items",
                invoice_value=matching_result.line_items_total,
                po_value=matching_result.line_items_matched,
                details=f"{unmatched_count} invoice line item(s) could not be matched to PO.",
                recommended_action=RecommendedAction.FLAG_FOR_REVIEW,
                confidence=0.90,
            ))
        
        reasoning = self._build_reasoning(discrepancies, total_variance, extracted, po)
        
        return DiscrepancyResult(
            discrepancies_found=len(discrepancies),
            discrepancies=discrepancies,
            price_variances=price_variances,
            quantity_variances=quantity_variances,
            total_variance=total_variance,
            agent_reasoning=reasoning,
        )
    
    def _compare_line_items(
        self,
        invoice_items: List[ExtractedLineItem],
        po_items: List[POLineItem]
    ) -> List[Discrepancy]:
        
        discrepancies = []
        po_descriptions = [item.description for item in po_items]
        
        for idx, inv_item in enumerate(invoice_items):
            match_result = fuzzy_match_product(inv_item.description, po_descriptions, threshold=70.0)
            
            if not match_result:
                discrepancies.append(Discrepancy(
                    type=DiscrepancyType.ITEM_NOT_FOUND,
                    severity=Severity.MEDIUM,
                    line_item_index=idx,
                    field="description",
                    invoice_value=inv_item.description,
                    po_value=None,
                    details=f"Invoice item '{inv_item.description}' not found in PO.",
                    recommended_action=RecommendedAction.FLAG_FOR_REVIEW,
                    confidence=0.85,
                ))
                continue
            
            po_idx, _, match_conf = match_result
            po_item = po_items[po_idx]
            
            price_variance_pct = self._calculate_percentage_variance(
                inv_item.unit_price, po_item.unit_price
            )
            
            if abs(price_variance_pct) > self.thresholds.PRICE_TOLERANCE_PERCENT:
                severity = self._determine_price_severity(price_variance_pct)
                action = self._determine_price_action(price_variance_pct)
                
                discrepancies.append(Discrepancy(
                    type=DiscrepancyType.PRICE_MISMATCH,
                    severity=severity,
                    line_item_index=idx,
                    field="unit_price",
                    invoice_value=inv_item.unit_price,
                    po_value=po_item.unit_price,
                    variance_percentage=price_variance_pct,
                    details=(
                        f"Line item {idx+1} ({inv_item.description}): "
                        f"Invoice price £{inv_item.unit_price:.2f} vs PO price £{po_item.unit_price:.2f} "
                        f"({price_variance_pct:+.1f}% variance)."
                    ),
                    recommended_action=action,
                    confidence=0.99,
                ))
            
            qty_variance_pct = self._calculate_percentage_variance(
                inv_item.quantity, po_item.quantity
            )
            
            if abs(qty_variance_pct) > 0:
                severity = Severity.MEDIUM if abs(qty_variance_pct) > 10 else Severity.LOW
                
                discrepancies.append(Discrepancy(
                    type=DiscrepancyType.QUANTITY_MISMATCH,
                    severity=severity,
                    line_item_index=idx,
                    field="quantity",
                    invoice_value=inv_item.quantity,
                    po_value=po_item.quantity,
                    variance_percentage=qty_variance_pct,
                    details=(
                        f"Line item {idx+1} ({inv_item.description}): "
                        f"Invoice quantity {inv_item.quantity} {inv_item.unit} vs "
                        f"PO quantity {po_item.quantity} {po_item.unit} "
                        f"({qty_variance_pct:+.1f}% variance)."
                    ),
                    recommended_action=RecommendedAction.FLAG_FOR_REVIEW,
                    confidence=0.99,
                ))
        
        return discrepancies
    
    def _calculate_percentage_variance(self, invoice_value: float, po_value: float) -> float:
        
        if po_value == 0:
            return 100.0 if invoice_value > 0 else 0.0
        
        return ((invoice_value - po_value) / po_value) * 100
    
    def _determine_price_severity(self, variance_pct: float) -> Severity:
        
        abs_variance = abs(variance_pct)
        
        if abs_variance > self.thresholds.PRICE_VARIANCE_ESCALATE:
            return Severity.CRITICAL
        elif abs_variance > self.thresholds.PRICE_VARIANCE_REVIEW_MIN:
            return Severity.HIGH
        elif abs_variance > self.thresholds.PRICE_TOLERANCE_PERCENT:
            return Severity.MEDIUM
        else:
            return Severity.LOW
    
    def _determine_price_action(self, variance_pct: float) -> RecommendedAction:
        
        abs_variance = abs(variance_pct)
        
        if abs_variance > self.thresholds.PRICE_VARIANCE_ESCALATE:
            return RecommendedAction.ESCALATE_TO_HUMAN
        elif abs_variance > self.thresholds.PRICE_VARIANCE_REVIEW_MIN:
            return RecommendedAction.FLAG_FOR_REVIEW
        else:
            return RecommendedAction.AUTO_APPROVE
    
    def _calculate_total_variance(self, invoice_total: float, po_total: float) -> TotalVariance:
        
        amount = invoice_total - po_total
        percentage = self._calculate_percentage_variance(invoice_total, po_total)
        
        within_amount_tolerance = abs(amount) <= self.thresholds.TOTAL_VARIANCE_AMOUNT
        within_percent_tolerance = abs(percentage) <= self.thresholds.TOTAL_VARIANCE_PERCENT
        
        within_tolerance = within_amount_tolerance or within_percent_tolerance
        
        return TotalVariance(
            amount=amount,
            percentage=percentage,
            within_tolerance=within_tolerance,
        )
    
    def _build_reasoning(
        self,
        discrepancies: List[Discrepancy],
        total_variance: TotalVariance,
        extracted,
        po
    ) -> str:
        
        if not discrepancies:
            return (
                f"No discrepancies detected. All line items match PO {po.po_number} exactly. "
                f"Total variance: £{total_variance.amount:.2f} ({total_variance.percentage:.1f}%). "
                f"Supplier verified. All checks passed."
            )
        
        price_issues = [d for d in discrepancies if d.type == DiscrepancyType.PRICE_MISMATCH]
        qty_issues = [d for d in discrepancies if d.type == DiscrepancyType.QUANTITY_MISMATCH]
        other_issues = [d for d in discrepancies if d.type not in [DiscrepancyType.PRICE_MISMATCH, DiscrepancyType.QUANTITY_MISMATCH]]
        
        parts = [f"Found {len(discrepancies)} discrepancy(ies) comparing invoice to PO {po.po_number}."]
        
        if price_issues:
            critical_prices = [d for d in price_issues if d.severity in [Severity.CRITICAL, Severity.HIGH]]
            if critical_prices:
                parts.append(
                    f"CRITICAL: {len(critical_prices)} significant price variance(s) detected - "
                    f"highest variance: {max(abs(d.variance_percentage or 0) for d in critical_prices):.1f}%."
                )
        
        if qty_issues:
            parts.append(f"Quantity mismatches: {len(qty_issues)} item(s).")
        
        if other_issues:
            issue_types = set(d.type.value for d in other_issues)
            parts.append(f"Other issues: {', '.join(issue_types)}.")
        
        parts.append(
            f"Total variance: £{total_variance.amount:.2f} ({total_variance.percentage:.1f}%) - "
            f"{'within' if total_variance.within_tolerance else 'OUTSIDE'} tolerance."
        )
        
        return " ".join(parts)
