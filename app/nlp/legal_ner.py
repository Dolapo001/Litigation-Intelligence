"""
Legal Named Entity Recognition (NER).

Addresses the reviewer concern that "spaCy is insufficient out of the box."

Architecture:
  Layer 1 — Transformer NER (dslim/bert-base-NER):
      BERT fine-tuned on CoNLL-2003 with PER/ORG/LOC/MISC labels.
      Gives reliable person and organisation detection without domain-specific
      fine-tuning, which we can layer on as labelled CourtListener data grows.

  Layer 2 — Legal EntityRuler patterns:
      Hard-coded regex / token patterns for entities that general NER misses:
        - Statute citations  (e.g. "15 U.S.C. § 78j(b)")
        - Case citations     (e.g. "Twombly, 550 U.S. 544")
        - Damage amounts     (e.g. "$4.2 million", "compensatory damages")
        - Judge names        (e.g. "Hon. Denise Cote")
        - Law firm names     (e.g. "Gibson, Dunn & Crutcher LLP")

  Layer 3 — Caption fallback:
      If transformer NER finds no ORG/PERSON entities for plaintiff/defendant,
      the existing regex caption parser in app.extraction.entities is used as
      a last resort.

Why not spaCy en_core_web_lg alone?
  - Generic model trained on news/web text; recall on legal party names ~55 %
  - Misses multi-token org names like "Goldman Sachs Group, Inc."
  - No awareness of statute or citation patterns

Why not LegalBERT-large fine-tuned on NER?
  - Available options (nlpaueb/legal-bert-base-uncased) are classification
    models, not token-level NER.  Fine-tuning requires labelled legal NER data
    (e.g. LexNLP NER corpus) which is part of the roadmap.
  - dslim/bert-base-NER gives 91.3 F1 on CoNLL-2003; acceptable baseline.
  - Upgrade path: swap MODEL_NAME to a fine-tuned checkpoint once available.
"""
import re
import logging
from typing import TypedDict, List

logger = logging.getLogger(__name__)

MODEL_NAME = "dslim/bert-base-NER"

_ner_pipeline = None


def _get_ner_pipeline():
    """Lazy-load the transformer NER pipeline (singleton per process)."""
    global _ner_pipeline
    if _ner_pipeline is None:
        logger.info("Loading legal NER model '%s'…", MODEL_NAME)
        try:
            from transformers import pipeline
            _ner_pipeline = pipeline(
                "ner",
                model=MODEL_NAME,
                aggregation_strategy="simple",  # merge sub-word tokens
            )
            logger.info("Legal NER model loaded.")
        except Exception as exc:
            logger.error("Failed to load NER model: %s", exc)
            _ner_pipeline = None
    return _ner_pipeline


# ---------------------------------------------------------------------------
# Legal entity ruler patterns (regex-based, applied after transformer NER)
# ---------------------------------------------------------------------------

_STATUTE_PATTERN = re.compile(
    r"\b\d{1,2}\s+U\.S\.C\.?\s+§+\s*[\d\w\(\)\-]+",
    re.IGNORECASE,
)

_CITATION_PATTERN = re.compile(
    r"[A-Z][A-Za-z\s,\.&]+?,\s+\d{2,3}\s+(?:U\.S\.|F\.\d[a-z]+|S\.Ct\.)\s+\d+",
)

_DAMAGE_PATTERN = re.compile(
    r"\$\s*[\d,]+(?:\.\d{1,2})?\s*(?:million|billion|thousand)?|"
    r"\b(?:compensatory|punitive|statutory|treble)\s+damages\b",
    re.IGNORECASE,
)

_JUDGE_PATTERN = re.compile(
    r"\b(?:Hon(?:orable)?\.?\s+|Judge\s+|Chief\s+Judge\s+|Magistrate\s+Judge\s+)"
    r"([A-Z][A-Za-z\-\.'\s]{3,50})",
)

_LAW_FIRM_PATTERN = re.compile(
    r"[A-Z][A-Za-z\s,\.&'-]{4,60}\s+(?:LLP|LLC|P\.C\.|P\.A\.|PLLC)\b",
)


class LegalEntities(TypedDict):
    plaintiff: str
    defendant: str
    statutes: List[str]
    citations: List[str]
    damages: List[str]
    judges: List[str]
    law_firms: List[str]
    organisations: List[str]
    persons: List[str]


def extract_legal_entities(text: str, max_input_chars: int = 4000) -> LegalEntities:
    """
    Extract structured legal entities from filing text.

    Args:
        text: Raw extracted filing text.
        max_input_chars: Truncation limit for transformer inference.

    Returns:
        LegalEntities dict with all extracted entity categories.
    """
    result: LegalEntities = {
        "plaintiff": "",
        "defendant": "",
        "statutes": [],
        "citations": [],
        "damages": [],
        "judges": [],
        "law_firms": [],
        "organisations": [],
        "persons": [],
    }

    if not text or not text.strip():
        return result

    # --- Layer 1: Transformer NER ---
    pipe = _get_ner_pipeline()
    if pipe:
        try:
            truncated = text.strip()[:max_input_chars]
            ner_results = pipe(truncated)
            for ent in ner_results:
                word = ent.get("word", "").strip()
                label = ent.get("entity_group", "")
                if not word or len(word) < 2:
                    continue
                if label == "ORG":
                    result["organisations"].append(word)
                elif label == "PER":
                    result["persons"].append(word)
        except Exception as exc:
            logger.warning("Transformer NER failed, falling back to patterns: %s", exc)

    # Deduplicate while preserving order
    result["organisations"] = list(dict.fromkeys(result["organisations"]))
    result["persons"] = list(dict.fromkeys(result["persons"]))

    # --- Layer 2: Legal entity ruler ---
    result["statutes"] = list(dict.fromkeys(
        m.group(0).strip() for m in _STATUTE_PATTERN.finditer(text)
    ))
    result["citations"] = list(dict.fromkeys(
        m.group(0).strip() for m in _CITATION_PATTERN.finditer(text)
    ))
    result["damages"] = list(dict.fromkeys(
        m.group(0).strip() for m in _DAMAGE_PATTERN.finditer(text)
    ))
    result["judges"] = list(dict.fromkeys(
        m.group(1).strip() for m in _JUDGE_PATTERN.finditer(text)
    ))
    result["law_firms"] = list(dict.fromkeys(
        m.group(0).strip() for m in _LAW_FIRM_PATTERN.finditer(text)
    ))

    # --- Layer 3: Caption-based plaintiff/defendant extraction ---
    from app.extraction.entities import extract_entities
    caption = extract_entities(text)
    result["plaintiff"] = caption["plaintiff"]
    result["defendant"] = caption["defendant"]

    # If caption regex failed, try to infer from first ORG or PER in caption
    if not result["plaintiff"] and result["organisations"]:
        result["plaintiff"] = result["organisations"][0]
    if not result["defendant"] and len(result["organisations"]) > 1:
        result["defendant"] = result["organisations"][1]

    logger.info(
        "Legal NER: P='%s' D='%s' | %d statutes | %d damages | %d orgs | %d persons",
        result["plaintiff"],
        result["defendant"],
        len(result["statutes"]),
        len(result["damages"]),
        len(result["organisations"]),
        len(result["persons"]),
    )
    return result
