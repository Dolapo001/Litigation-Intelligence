"""
Tests for app/processing/pdf_extractor.py

Uses mocks for fitz, pdf2image, and pytesseract so no real PDFs are needed.
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

import app.processing.pdf_extractor as extractor


class TestExtractTextNative:
    def test_returns_text_from_all_pages(self):
        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = "Page one text. "
        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = "Page two text."

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page1, mock_page2]))

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            result = extractor.extract_text_native("dummy.pdf")

        assert "Page one text." in result
        assert "Page two text." in result

    def test_returns_empty_on_exception(self):
        mock_fitz = MagicMock()
        mock_fitz.open.side_effect = Exception("corrupt pdf")

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            result = extractor.extract_text_native("bad.pdf")

        assert result == ""

    def test_returns_empty_when_fitz_not_installed(self):
        with patch.dict("sys.modules", {"fitz": None}):
            result = extractor.extract_text_native("dummy.pdf")
        assert result == ""


class TestExtractTextOcr:
    def test_runs_tesseract_on_each_page(self):
        mock_img1 = MagicMock()
        mock_img2 = MagicMock()

        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [mock_img1, mock_img2]

        mock_tess = MagicMock()
        mock_tess.image_to_string.side_effect = ["OCR page one", "OCR page two"]

        with patch.dict("sys.modules", {"pdf2image": mock_pdf2image, "pytesseract": mock_tess}):
            result = extractor.extract_text_ocr("dummy.pdf")

        assert "OCR page one" in result
        assert "OCR page two" in result
        assert mock_tess.image_to_string.call_count == 2

    def test_returns_empty_on_exception(self):
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.side_effect = Exception("poppler missing")

        mock_tess = MagicMock()

        with patch.dict("sys.modules", {"pdf2image": mock_pdf2image, "pytesseract": mock_tess}):
            result = extractor.extract_text_ocr("dummy.pdf")

        assert result == ""


class TestExtractText:
    def test_returns_native_when_long_enough(self):
        long_text = "A" * 600
        with patch.object(extractor, "extract_text_native", return_value=long_text), \
             patch("pathlib.Path.exists", return_value=True):
            result = extractor.extract_text("dummy.pdf")
        assert result == long_text

    def test_falls_back_to_ocr_when_native_too_short(self):
        short_text = "short"
        ocr_text = "B" * 800

        with patch.object(extractor, "extract_text_native", return_value=short_text), \
             patch.object(extractor, "extract_text_ocr", return_value=ocr_text), \
             patch("pathlib.Path.exists", return_value=True):
            result = extractor.extract_text("dummy.pdf")

        assert result == ocr_text

    def test_returns_native_if_ocr_shorter(self):
        native_text = "C" * 100
        ocr_text = "D" * 10

        with patch.object(extractor, "extract_text_native", return_value=native_text), \
             patch.object(extractor, "extract_text_ocr", return_value=ocr_text), \
             patch("pathlib.Path.exists", return_value=True):
            result = extractor.extract_text("dummy.pdf", min_length=500)

        assert result == native_text

    def test_returns_empty_when_file_missing(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = extractor.extract_text("nonexistent.pdf")
        assert result == ""
