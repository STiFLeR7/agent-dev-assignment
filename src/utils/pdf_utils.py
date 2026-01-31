import fitz
from pathlib import Path
from typing import Tuple, Optional
import base64
import io

try:
    from pdf2image import convert_from_path
    from PIL import Image
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

def extract_text_from_pdf(pdf_path: str) -> Tuple[str, float, str]:
    
    pdf_path = Path(pdf_path)
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    doc = fitz.open(str(pdf_path))
    text = ""
    
    for page in doc:
        text += page.get_text()
    
    doc.close()
    
    if len(text.strip()) > 100:
        confidence = 0.95
        quality = "excellent"
    elif len(text.strip()) > 50:
        confidence = 0.85
        quality = "good"
    else:
        confidence = 0.70
        quality = "requires_ocr"
    
    return text, confidence, quality

def extract_text_with_ocr(pdf_path: str) -> Tuple[str, float, str]:
    
    if not HAS_OCR:
        raise RuntimeError("OCR dependencies not installed. Install pdf2image, Pillow, and pytesseract.")
    
    pdf_path = Path(pdf_path)
    
    images = convert_from_path(str(pdf_path), dpi=300)
    
    text_parts = []
    for image in images:
        text = pytesseract.image_to_string(image)
        text_parts.append(text)
    
    full_text = "\n".join(text_parts)
    
    if len(full_text.strip()) > 200:
        confidence = 0.80
        quality = "acceptable"
    elif len(full_text.strip()) > 100:
        confidence = 0.70
        quality = "poor"
    else:
        confidence = 0.50
        quality = "very_poor"
    
    return full_text, confidence, quality

def pdf_to_base64_images(pdf_path: str, dpi: int = 150) -> list:
    
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    
    images = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat)
        
        img_bytes = pix.tobytes("png")
        
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        images.append(img_base64)
    
    doc.close()
    return images

def get_pdf_info(pdf_path: str) -> dict:
    
    pdf_path = Path(pdf_path)
    
    doc = fitz.open(str(pdf_path))
    info = {
        "filename": pdf_path.name,
        "file_size_kb": pdf_path.stat().st_size / 1024,
        "page_count": len(doc),
        "metadata": doc.metadata,
    }
    doc.close()
    
    return info
