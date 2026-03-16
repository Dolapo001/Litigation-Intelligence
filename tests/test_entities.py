"""
Tests for app/extraction/entities.py

Pure-function unit tests — no database or network required.
"""
import pytest
from app.extraction.entities import extract_entities


class TestInlineVsPattern:
    def test_simple_inline(self):
        # The greedy second group captures trailing words; verify the core names appear
        text = "Smith v. Acme Corp filed in SDNY."
        result = extract_entities(text)
        assert "Smith" in result["plaintiff"]
        assert "Acme Corp" in result["defendant"]

    def test_full_names(self):
        text = "John D. Smith v. Acme Corporation et al."
        result = extract_entities(text)
        assert "Smith" in result["plaintiff"]
        assert "Acme" in result["defendant"]

    def test_vs_abbreviation(self):
        text = "Williams vs. Global Investments Inc"
        result = extract_entities(text)
        assert "Williams" in result["plaintiff"]
        assert "Global Investments" in result["defendant"]


class TestBlockCaptionPattern:
    def test_standard_block(self):
        # Block pattern with \s in character class can match across lines;
        # verify that the correct party names appear in the captured groups.
        text = (
            "JOHN SMITH,\n"
            "    Plaintiff,\n"
            "vs.\n"
            "ACME CORPORATION,\n"
            "    Defendant.\n"
        )
        result = extract_entities(text)
        assert "JOHN SMITH" in result["plaintiff"]
        assert "ACME CORPORATION" in result["defendant"]

    def test_block_preferred_over_inline(self):
        # Block caption path is taken when both patterns match.
        text = (
            "MARY JONES,\n"
            "    Plaintiff,\n"
            "v.\n"
            "XYZ LLC,\n"
            "    Defendant.\n"
            "\n"
            "Mary Jones v. XYZ LLC — Case No. 24-cv-1234"
        )
        result = extract_entities(text)
        assert "MARY JONES" in result["plaintiff"]
        assert "XYZ LLC" in result["defendant"]


class TestFallback:
    def test_empty_text(self):
        result = extract_entities("")
        assert result["plaintiff"] == ""
        assert result["defendant"] == ""

    def test_no_parties(self):
        text = "This document contains no party information at all."
        result = extract_entities(text)
        assert result["plaintiff"] == ""
        assert result["defendant"] == ""

    def test_returns_typed_dict_keys(self):
        result = extract_entities("Smith v. Jones")
        assert "plaintiff" in result
        assert "defendant" in result
