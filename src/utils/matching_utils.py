from typing import List, Tuple, Optional
from rapidfuzz import fuzz, process

def fuzzy_match_string(query: str, choices: List[str], threshold: float = 70.0) -> Optional[Tuple[str, float]]:
    
    if not query or not choices:
        return None
    
    result = process.extractOne(query, choices, scorer=fuzz.ratio)
    
    if result and result[1] >= threshold:
        return (result[0], result[1] / 100.0)
    
    return None

def fuzzy_match_product(
    invoice_description: str, 
    po_descriptions: List[str],
    threshold: float = 70.0
) -> Optional[Tuple[int, str, float]]:
    
    if not invoice_description or not po_descriptions:
        return None
    
    query = invoice_description.lower().strip()
    choices = [d.lower().strip() for d in po_descriptions]
    
    result = process.extractOne(query, choices, scorer=fuzz.token_sort_ratio)
    
    if result and result[1] >= threshold:
        index = choices.index(result[0])
        return (index, po_descriptions[index], result[1] / 100.0)
    
    return None

def calculate_overall_match_confidence(
    supplier_match: bool,
    date_match: bool,
    product_match_rate: float,
    price_match_rate: float,
    has_po_reference: bool
) -> float:
    
    weights = {
        "po_reference": 0.35,
        "supplier": 0.20,
        "products": 0.25,
        "prices": 0.15,
        "date": 0.05,
    }
    
    score = 0.0
    
    if has_po_reference:
        score += weights["po_reference"] * 1.0
    
    if supplier_match:
        score += weights["supplier"] * 1.0
    
    score += weights["products"] * product_match_rate
    score += weights["prices"] * price_match_rate
    
    if date_match:
        score += weights["date"] * 1.0
    
    return min(score, 1.0)

def normalize_supplier_name(name: str) -> str:
    
    if not name:
        return ""
    
    name = name.lower().strip()
    
    suffixes = [
        " ltd", " ltd.", " limited", " inc", " inc.", " incorporated",
        " plc", " llc", " corp", " corporation", " co", " co.",
        " gmbh", " ag", " ab", " sa", " srl"
    ]
    
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    
    return name.strip()

def compare_suppliers(supplier1: str, supplier2: str, threshold: float = 80.0) -> Tuple[bool, float]:
    
    norm1 = normalize_supplier_name(supplier1)
    norm2 = normalize_supplier_name(supplier2)
    
    if norm1 == norm2:
        return (True, 1.0)
    
    score = fuzz.ratio(norm1, norm2)
    
    return (score >= threshold, score / 100.0)
