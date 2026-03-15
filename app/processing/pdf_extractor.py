"""
PDF text extraction.

Attempts native text extraction via PyMuPDF first.
Falls back to Tesseract OCR when the extracted text is too short
(e.g., scanned documents).
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_native(pdf_path: str) -> str:
    """
    Extract embedded text from a PDF using PyMuPDF (fitz).
    Returns the concatenated text of all pages, or empty string on failure.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF (fitz) is not installed.")
        return ""

    text_parts = []
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
    except Exception as exc:
        logger.error("PyMuPDF extraction failed for %s: %s", pdf_path, exc)
    return "\n".join(text_parts)


def extract_text_ocr(pdf_path: str, dpi: int = 200) -> str:
    """
    Convert each page to an image and run Tesseract OCR.
    Used as a fallback when native extraction yields insufficient text.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as exc:
        logger.error("OCR dependencies not installed: %s", exc)
        return ""

    text_parts = []
    try:
        images = convert_from_path(pdf_path, dpi=dpi)
        for i, img in enumerate(images):
            page_text = pytesseract.image_to_string(img)
            text_parts.append(page_text)
            logger.debug("OCR page %d: %d chars", i + 1, len(page_text))
    except Exception as exc:
        logger.error("OCR failed for %s: %s", pdf_path, exc)
    return "\n".join(text_parts)


def extract_text(pdf_path: str, min_length: int = 500) -> str:
    """
    Primary extraction entry point.

    1. Try native text extraction.
    2. If result is shorter than `min_length` characters, fall back to OCR.
    3. Return whichever result is longer.
    """
    if not Path(pdf_path).exists():
        logger.error("PDF file not found: %s", pdf_path)
        return ""

    native_text = extract_text_native(pdf_path)
    if len(native_text.strip()) >= min_length:
        logger.info("Native extraction succeeded (%d chars).", len(native_text))
        return native_text

    logger.info(
        "Native text too short (%d chars < %d). Falling back to OCR.",
        len(native_text.strip()),
        min_length,
    )
    ocr_text = extract_text_ocr(pdf_path)
    logger.info("OCR extraction returned %d chars.", len(ocr_text))
    return ocr_text if len(ocr_text) > len(native_text) else native_text
