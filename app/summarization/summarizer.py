"""
Summarization module.

Uses a HuggingFace transformer pipeline to generate 1–3 sentence
summaries of filing text.

The pipeline is loaded lazily and cached in the module namespace so
the model is only downloaded and initialized once per worker process.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_pipeline = None
_MODEL_NAME = "facebook/bart-large-cnn"


def _get_pipeline():
    """Lazy-load the summarization pipeline (cached after first call)."""
    global _pipeline
    if _pipeline is None:
        logger.info("Loading summarization model '%s' (first run may download weights)…", _MODEL_NAME)
        try:
            from transformers import pipeline
            _pipeline = pipeline("summarization", model=_MODEL_NAME)
            logger.info("Summarization model loaded successfully.")
        except Exception as exc:
            logger.error("Failed to load summarization model: %s", exc)
            _pipeline = None
    return _pipeline


def generate_summary(text: str, max_input_chars: int = 2000) -> str:
    """
    Generate a concise 1–3 sentence summary of `text`.

    Args:
        text: Raw extracted filing text.
        max_input_chars: Truncation limit before passing text to the model.

    Returns:
        Summary string, or empty string if summarization fails.
    """
    if not text or not text.strip():
        return ""

    # Truncate to avoid exceeding the model's token limit.
    truncated = text.strip()[:max_input_chars]

    pipe = _get_pipeline()
    if pipe is None:
        logger.warning("Summarizer unavailable — returning empty summary.")
        return ""

    try:
        result = pipe(
            truncated,
            max_length=130,
            min_length=30,
            do_sample=False,
            truncation=True,
        )
        summary = result[0]["summary_text"]
        logger.info("Generated summary (%d chars).", len(summary))
        return summary
    except Exception as exc:
        logger.error("Summarization failed: %s", exc)
        return ""
