import json
from typing import List, Optional, Tuple
from datetime import datetime, timedelta

from ..models import (
    MatchingResult,
    ExtractionResult,
    PurchaseOrder,
    POLineItem,
    AlternativeMatch,
    MatchMethod,
    ExtractedLineItem,
)
from ..utils.matching_utils import (
    fuzzy_match_product,
    compare_suppliers,
    normalize_supplier_name,
    calculate_overall_match_confidence,
)
from ..config import ReconciliationThresholds

class MatchingAgent:
    
    
    def __init__(self):
        
        self.name = "Matching Agent"
        self.thresholds = ReconciliationThresholds()
    
    def process(
        self, 
        extraction_result: ExtractionResult,
        po_database: List[PurchaseOrder]
    ) -> MatchingResult:
        
        extracted = extraction_result.extracted_data
        
        if extracted.po_reference:
            result = self._match_by_po_reference(extracted.po_reference, extracted, po_database)
            if result.po_match_confidence >= 0.90:
                return result
        
        result = self._match_by_supplier_date_products(extracted, po_database)
        if result.po_match_confidence >= 0.70:
            alternatives = self._find_alternative_matches(extracted, po_database, exclude=result.matched_po)
            result.alternative_matches = alternatives[:3]
            return result
        
        result = self._match_by_products_only(extracted, po_database)
        alternatives = self._find_alternative_matches(extracted, po_database, exclude=result.matched_po)
        result.alternative_matches = alternatives[:3]
        
        return result
    
    def _match_by_po_reference(
        self,
        po_reference: str,
        extracted,
        po_database: List[PurchaseOrder]
    ) -> MatchingResult:
        
        po_ref_normalized = po_reference.strip().upper()
        
        for po in po_database:
            if po.po_number.strip().upper() == po_ref_normalized:
                supplier_match, supplier_conf = compare_suppliers(
                    extracted.supplier_name, po.supplier
                )
                
                line_match_count, line_match_details = self._match_line_items(
                    extracted.line_items, po.line_items
                )
                
                match_rate = line_match_count / len(extracted.line_items) if extracted.line_items else 0
                
                confidence = 0.95 if supplier_match else 0.85
                if match_rate < 1.0:
                    confidence -= (1.0 - match_rate) * 0.10
                
                date_variance = self._calculate_date_variance(extracted.invoice_date, po.date)
                
                reasoning = (
                    f"Exact PO reference match found: {po.po_number}. "
                    f"Supplier {'matches' if supplier_match else 'MISMATCH'}: "
                    f"'{extracted.supplier_name}' vs '{po.supplier}'. "
                    f"Line items matched: {line_match_count}/{len(extracted.line_items)} "
                    f"({match_rate*100:.0f}% match rate). "
                    f"Date variance: {date_variance} days. "
                    f"Match confidence: {confidence*100:.1f}%."
                )
                
                return MatchingResult(
                    po_match_confidence=confidence,
                    matched_po=po.po_number,
                    matched_po_data=po,
                    match_method=MatchMethod.EXACT_PO_REFERENCE,
                    supplier_match=supplier_match,
                    date_variance_days=date_variance,
                    line_items_matched=line_match_count,
                    line_items_total=len(extracted.line_items),
                    match_rate=match_rate,
                    alternative_matches=[],
                    agent_reasoning=reasoning,
                )
        
        return MatchingResult(
            po_match_confidence=0.0,
            matched_po=None,
            matched_po_data=None,
            match_method=MatchMethod.NO_MATCH,
            supplier_match=False,
            date_variance_days=None,
            line_items_matched=0,
            line_items_total=len(extracted.line_items),
            match_rate=0.0,
            alternative_matches=[],
            agent_reasoning=f"PO reference '{po_reference}' not found in database. Will attempt fuzzy matching.",
        )
    
    def _match_by_supplier_date_products(
        self,
        extracted,
        po_database: List[PurchaseOrder]
    ) -> MatchingResult:
        
        best_match = None
        best_confidence = 0.0
        
        for po in po_database:
            supplier_match, supplier_conf = compare_suppliers(extracted.supplier_name, po.supplier)
            
            if not supplier_match and supplier_conf < 0.60:
                continue
            
            date_variance = self._calculate_date_variance(extracted.invoice_date, po.date)
            date_match = date_variance is not None and abs(date_variance) <= self.thresholds.DATE_RANGE_DAYS
            
            line_match_count, _ = self._match_line_items(extracted.line_items, po.line_items)
            product_match_rate = line_match_count / len(extracted.line_items) if extracted.line_items else 0
            
            if product_match_rate < self.thresholds.PRODUCT_MATCH_THRESHOLD:
                continue
            
            confidence = calculate_overall_match_confidence(
                supplier_match=supplier_match,
                date_match=date_match,
                product_match_rate=product_match_rate,
                price_match_rate=0.8,
                has_po_reference=False,
            )
            
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = (po, supplier_match, date_variance, line_match_count, product_match_rate)
        
        if best_match:
            po, supplier_match, date_variance, line_match_count, match_rate = best_match
            
            reasoning = (
                f"Fuzzy match by supplier + date + products: {po.po_number}. "
                f"Supplier match: '{extracted.supplier_name}' ~ '{po.supplier}'. "
                f"Line items matched: {line_match_count}/{len(extracted.line_items)} "
                f"({match_rate*100:.0f}% match rate). "
                f"Date variance: {date_variance} days. "
                f"Match confidence: {best_confidence*100:.1f}%."
            )
            
            return MatchingResult(
                po_match_confidence=best_confidence,
                matched_po=po.po_number,
                matched_po_data=po,
                match_method=MatchMethod.SUPPLIER_DATE_PRODUCT,
                supplier_match=supplier_match,
                date_variance_days=date_variance,
                line_items_matched=line_match_count,
                line_items_total=len(extracted.line_items),
                match_rate=match_rate,
                alternative_matches=[],
                agent_reasoning=reasoning,
            )
        
        return MatchingResult(
            po_match_confidence=0.0,
            matched_po=None,
            matched_po_data=None,
            match_method=MatchMethod.NO_MATCH,
            supplier_match=False,
            date_variance_days=None,
            line_items_matched=0,
            line_items_total=len(extracted.line_items),
            match_rate=0.0,
            alternative_matches=[],
            agent_reasoning="No match found by supplier + date + products. Will try product-only matching.",
        )
    
    def _match_by_products_only(
        self,
        extracted,
        po_database: List[PurchaseOrder]
    ) -> MatchingResult:
        
        best_match = None
        best_confidence = 0.0
        
        for po in po_database:
            line_match_count, matched_details = self._match_line_items(
                extracted.line_items, po.line_items, threshold=75.0
            )
            
            product_match_rate = line_match_count / len(extracted.line_items) if extracted.line_items else 0
            
            if product_match_rate < self.thresholds.PRODUCT_ONLY_MATCH_THRESHOLD:
                continue
            
            supplier_match, supplier_conf = compare_suppliers(extracted.supplier_name, po.supplier)
            
            confidence = 0.40 + (product_match_rate * 0.30) + (supplier_conf * 0.15)
            
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = (po, supplier_match, line_match_count, product_match_rate)
        
        if best_match:
            po, supplier_match, line_match_count, match_rate = best_match
            date_variance = self._calculate_date_variance(extracted.invoice_date, po.date)
            
            reasoning = (
                f"Product-only fuzzy match found: {po.po_number}. "
                f"Products matched: {line_match_count}/{len(extracted.line_items)} "
                f"({match_rate*100:.0f}% match rate). "
                f"Supplier '{extracted.supplier_name}' vs '{po.supplier}' "
                f"({'matches' if supplier_match else 'different'}). "
                f"Lower confidence due to missing PO reference: {best_confidence*100:.1f}%."
            )
            
            return MatchingResult(
                po_match_confidence=best_confidence,
                matched_po=po.po_number,
                matched_po_data=po,
                match_method=MatchMethod.PRODUCT_ONLY_FUZZY,
                supplier_match=supplier_match,
                date_variance_days=date_variance,
                line_items_matched=line_match_count,
                line_items_total=len(extracted.line_items),
                match_rate=match_rate,
                alternative_matches=[],
                agent_reasoning=reasoning,
            )
        
        return MatchingResult(
            po_match_confidence=0.0,
            matched_po=None,
            matched_po_data=None,
            match_method=MatchMethod.NO_MATCH,
            supplier_match=False,
            date_variance_days=None,
            line_items_matched=0,
            line_items_total=len(extracted.line_items),
            match_rate=0.0,
            alternative_matches=[],
            agent_reasoning=(
                f"Could not find matching PO for invoice. "
                f"Supplier: {extracted.supplier_name}. "
                f"Products: {[item.description for item in extracted.line_items]}. "
                f"No PO in database matches with sufficient confidence."
            ),
        )
    
    def _match_line_items(
        self,
        invoice_items: List[ExtractedLineItem],
        po_items: List[POLineItem],
        threshold: float = 70.0
    ) -> Tuple[int, List[dict]]:
        
        matched = 0
        details = []
        po_descriptions = [item.description for item in po_items]
        used_indices = set()
        
        for inv_item in invoice_items:
            result = fuzzy_match_product(
                inv_item.description, 
                po_descriptions,
                threshold=threshold
            )
            
            if result:
                idx, matched_desc, confidence = result
                if idx not in used_indices:
                    used_indices.add(idx)
                    matched += 1
                    details.append({
                        "invoice_item": inv_item.description,
                        "po_item": matched_desc,
                        "confidence": confidence,
                        "po_index": idx,
                    })
        
        return matched, details
    
    def _find_alternative_matches(
        self,
        extracted,
        po_database: List[PurchaseOrder],
        exclude: Optional[str] = None
    ) -> List[AlternativeMatch]:
        
        alternatives = []
        
        for po in po_database:
            if exclude and po.po_number == exclude:
                continue
            
            line_match_count, _ = self._match_line_items(
                extracted.line_items, po.line_items, threshold=60.0
            )
            match_rate = line_match_count / len(extracted.line_items) if extracted.line_items else 0
            
            if match_rate >= 0.50:
                supplier_match, supplier_conf = compare_suppliers(
                    extracted.supplier_name, po.supplier
                )
                
                confidence = 0.30 + (match_rate * 0.40) + (supplier_conf * 0.20)
                
                alternatives.append(AlternativeMatch(
                    po_number=po.po_number,
                    confidence=confidence,
                    match_method=MatchMethod.PRODUCT_ONLY_FUZZY,
                    reasoning=f"{match_rate*100:.0f}% product match with {po.supplier}",
                ))
        
        alternatives.sort(key=lambda x: x.confidence, reverse=True)
        return alternatives
    
    def _calculate_date_variance(
        self, 
        invoice_date_str: Optional[str], 
        po_date_str: str
    ) -> Optional[int]:
        
        if not invoice_date_str:
            return None
        
        try:
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]:
                try:
                    invoice_date = datetime.strptime(invoice_date_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
            
            po_date = datetime.strptime(po_date_str, "%Y-%m-%d")
            return (invoice_date - po_date).days
        except Exception:
            return None
