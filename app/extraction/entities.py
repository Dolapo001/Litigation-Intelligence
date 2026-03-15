"""
Entity extraction from raw filing text.

Extracts plaintiff and defendant names using a layered approach:
1. Regex matching on canonical "Plaintiff v. Defendant" caption patterns.
2. Multi-line caption scanning for formatted complaint headings.
3. Graceful degradation to empty strings when no match is found.
"""
import re
import logging
from typing import TypedDict

logger = logging.getLogger(__name__)


class Entities(TypedDict):
    plaintiff: str
    defendant: str


# Pattern 1: Single-line "Smith v. Acme Corp" or "SMITH v. ACME CORP"
_INLINE_VS = re.compile(
    r"([A-Z][A-Za-z\s,\.'-]{2,60}?)\s+v(?:s?)\.\s+([A-Z][A-Za-z\s,\.'-]{2,60})",
    re.MULTILINE,
)

# Pattern 2: Multi-line complaint caption blocks commonly found in SDNY filings
#   JOHN SMITH,
#       Plaintiff,
#   vs.
#   ACME CORPORATION,
#       Defendant.
_BLOCK_PLAINTIFF = re.compile(
    r"([A-Z][A-Z\s,\.'-]+?),?\s*\n\s*Plaintiff",
    re.MULTILINE | re.IGNORECASE,
)
_BLOCK_DEFENDANT = re.compile(
    r"([A-Z][A-Z\s,\.'-]+?),?\s*\n\s*Defendant",
    re.MULTILINE | re.IGNORECASE,
)


def _clean(name: str) -> str:
    """Strip trailing punctuation and excess whitespace from a matched name."""
    return re.sub(r"[,;:\s]+$", "", name.strip())


def extract_entities(text: str) -> Entities:
    """
    Extract plaintiff and defendant from filing text.
    Returns a dict with 'plaintiff' and 'defendant' keys.
    """
    # --- Strategy 1: block-style caption (most accurate for complaints) ---
    p_match = _BLOCK_PLAINTIFF.search(text)
    d_match = _BLOCK_DEFENDANT.search(text)

    if p_match and d_match:
        plaintiff = _clean(p_match.group(1))
        defendant = _clean(d_match.group(1))
        if plaintiff and defendant:
            logger.info("Entities (block): P='%s' D='%s'", plaintiff, defendant)
            return {"plaintiff": plaintiff, "defendant": defendant}

    # --- Strategy 2: inline "X v. Y" pattern ---
    vs_match = _INLINE_VS.search(text)
    if vs_match:
        plaintiff = _clean(vs_match.group(1))
        defendant = _clean(vs_match.group(2))
        logger.info("Entities (inline): P='%s' D='%s'", plaintiff, defendant)
        return {"plaintiff": plaintiff, "defendant": defendant}

    logger.warning("Entity extraction found no parties in the text.")
    return {"plaintiff": "", "defendant": ""}
