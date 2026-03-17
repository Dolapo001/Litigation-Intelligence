#!/usr/bin/env python
"""
Litigation Intelligence — Court Filing Poller
=============================================

A standalone worker script that:
  1. Polls CourtListener for new SDNY dockets.
  2. Downloads the associated complaint PDF.
  3. FAST PATH  — digital PDFs: extract text natively, enrich synchronously.
  4. SLOW PATH  — scanned PDFs: save partial record immediately, enqueue
                  async OCR + NLP Celery task (never blocks the poll cycle).
  5. Enrichment pipeline (sync or via Celery):
       a. Legal NER      (dslim/bert-base-NER + legal entity ruler)
       b. Summarization  (distilBART-cnn-12-6, 3× faster than BART-large)
       c. Case type      (zero-shot, facebook/bart-large-mnli)
       d. Embeddings     (all-MiniLM-L6-v2, stored for similarity search)
       e. Risk scoring   (rule-based; XGBoost roadmap)
  6. Persists structured intelligence JSON to PostgreSQL.

Run this script independently of the Django dev server:
    python scripts/poll_courtlistener.py

Set POLL_INTERVAL_SECONDS=0 to run once (useful for CI / testing).
"""
import os
import sys
import time
import logging
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Bootstrap Django — must happen before any app imports
# ---------------------------------------------------------------------------
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()
# ---------------------------------------------------------------------------

from django.conf import settings

from app.ingestion.courtlistener import CourtListenerClient
from app.processing.pdf_extractor import extract_text, extract_text_native
from app.summarization.summarizer import generate_summary
from app.nlp.legal_ner import extract_legal_entities
from app.nlp.case_classifier import classify_case
from app.nlp.embeddings import generate_embedding, find_similar_filings
from app.nlp.risk_scorer import score_filing
from app.storage.repository import filing_exists, save_filing, log_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("poller")


def _extract_court_code(court_raw: str, default: str) -> str:
    """
    Return a clean court code from a raw value that may be a full URL or plain code.

    CourtListener sometimes returns the court field as a hyperlinked URL:
        "https://www.courtlistener.com/api/rest/v3/courts/dcd/?format=json"
    This function extracts just the short code ("dcd") and falls back to
    `default` when the code cannot be determined.
    """
    if not court_raw:
        return default

    if "/courts/" in court_raw:
        # Use urllib.parse to safely extract the path, then find the segment
        # after "courts".  This handles both trailing-slash and query-string
        # variants without fragile manual splitting.
        path = urlparse(court_raw).path          # "/api/rest/v3/courts/dcd/"
        segments = [s for s in path.split("/") if s]
        try:
            idx = segments.index("courts")
            code = segments[idx + 1] if idx + 1 < len(segments) else ""
        except (ValueError, IndexError):
            code = ""
        return code if code else default

    # Plain code — strip any accidental query-string fragment and whitespace.
    plain = court_raw.split("?")[0].strip()
    return plain if plain else default


def process_docket(client: CourtListenerClient, docket: dict) -> None:
    """
    Full pipeline for a single newly detected docket.
    """
    docket_id = str(docket["id"])
    case_name = docket.get("case_name", "Unknown v. Unknown")
    
    # Extract court code from URL if necessary.
    # CourtListener returns court as a hyperlink URL, e.g.:
    #   "https://www.courtlistener.com/api/rest/v3/courts/dcd/?format=json"
    # We need just the short code ("dcd").
    court_raw = docket.get("court", settings.TARGET_COURT)
    court = _extract_court_code(str(court_raw) if court_raw else "", settings.TARGET_COURT)

    date_filed = docket.get("date_filed")

    # --- Fetch court metadata (cached per client instance) ---
    court_meta = client.fetch_court(court)
    court_name = (court_meta.get("short_name") or "") if court_meta else ""
    court_full_name = (court_meta.get("full_name") or "") if court_meta else ""
    court_citation = (court_meta.get("citation_string") or "") if court_meta else ""

    logger.info("─" * 60)
    logger.info("New Filing Detected")
    logger.info("  Court    : %s (%s)", court, court_full_name or "unknown")
    logger.info("  Case     : %s", case_name)
    logger.info("  Docket ID: %s", docket_id)

    # --- Duplicate guard ---
    if filing_exists(docket_id):
        logger.info("  → Already processed. Skipping.")
        log_ingestion(docket_id, "skipped", "Duplicate docket.")
        return

    # --- Retrieve docket entries ---
    entries = client.fetch_docket_entries(docket_id)
    recap_entry = None
    for entry in entries:
        docs = entry.get("recap_documents", [])
        if docs:
            recap_entry = entry
            recap_doc_id = docs[0].get("id")
            break

    if not recap_entry:
        logger.warning("  → No RECAP documents found. Skipping PDF download.")
        log_ingestion(docket_id, "skipped", "No RECAP documents.")
        # Try to parse at least plaintiff/defendant from case name for better metadata
        fallback_p, fallback_d = "", ""
        if " v. " in case_name:
            parts = case_name.split(" v. ", 1)
            fallback_p, fallback_d = parts[0].strip(), parts[1].strip()

        save_filing(
            docket_id=docket_id,
            court=court,
            court_name=court_name,
            court_full_name=court_full_name,
            court_citation=court_citation,
            case_name=case_name,
            plaintiff=fallback_p,
            defendant=fallback_d,
            summary="No complaint document available.",
            pdf_path="",
            date_filed=date_filed,
        )
        return

    # --- Download PDF ---
    data_dir: Path = settings.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = data_dir / f"{docket_id}.pdf"

    doc_meta = client.fetch_recap_document(str(recap_doc_id))
    pdf_url = doc_meta.get("filepath_local") or doc_meta.get("filepath_pdf") if doc_meta else None

    if not pdf_url:
        logger.warning("  → PDF URL not available for docket %s.", docket_id)
        log_ingestion(docket_id, "error", "PDF URL not found in RECAP metadata.")
        return

    # Retry logic (up to 3 attempts)
    downloaded = False
    for attempt in range(1, 4):
        if client.download_pdf(pdf_url, str(pdf_path)):
            downloaded = True
            break
        logger.warning("  → Download attempt %d failed. Retrying…", attempt)
        time.sleep(2 ** attempt)

    if not downloaded:
        log_ingestion(docket_id, "error", f"PDF download failed after 3 attempts: {pdf_url}")
        return

    # --- FAST PATH: try native text extraction ---
    native_text = extract_text_native(str(pdf_path))
    is_scanned = len(native_text.strip()) < settings.PDF_TEXT_MIN_LENGTH

    if is_scanned:
        # SLOW PATH: scanned PDF detected
        # 1. Save partial record immediately so API returns something useful
        # 2. Enqueue async OCR task — this never blocks the poll cycle
        logger.info("  → Scanned PDF detected (native text: %d chars). Queuing OCR.", len(native_text.strip()))
        save_filing(
            docket_id=docket_id,
            court=court,
            court_name=court_name,
            court_full_name=court_full_name,
            court_citation=court_citation,
            case_name=case_name,
            plaintiff="",
            defendant="",
            summary="OCR processing in progress — check back shortly.",
            pdf_path=str(pdf_path),
            date_filed=date_filed,
            processing_status="ocr_queued",
        )
        # Enqueue async OCR (runs in Celery 'ocr' queue, ~15-40 s)
        try:
            from app.tasks.ocr_task import run_ocr
            run_ocr.apply_async(
                args=[docket_id, str(pdf_path)],
                queue="ocr",
            )
            log_ingestion(docket_id, "success", f"OCR queued: {case_name}")
            logger.info("  ✓ Partial record saved; OCR task enqueued.")
        except Exception as exc:
            logger.warning("  → Celery unavailable (%s). Running OCR synchronously.", exc)
            # Fallback: run OCR synchronously if Celery/Redis not available
            text = extract_text(str(pdf_path), min_length=settings.PDF_TEXT_MIN_LENGTH)
            _run_full_enrichment(
                docket_id=docket_id, text=text, court=court,
                court_name=court_name, court_full_name=court_full_name,
                court_citation=court_citation, case_name=case_name,
                pdf_path=str(pdf_path), date_filed=date_filed,
            )
        return

    # FAST PATH: digital PDF with embedded text
    text = native_text
    _run_full_enrichment(
        docket_id=docket_id, text=text, court=court,
        court_name=court_name, court_full_name=court_full_name,
        court_citation=court_citation, case_name=case_name,
        pdf_path=str(pdf_path), date_filed=date_filed,
    )


def _run_full_enrichment(
    docket_id: str,
    text: str,
    court: str,
    court_name: str,
    court_full_name: str,
    court_citation: str,
    case_name: str,
    pdf_path: str,
    date_filed,
) -> None:
    """
    Run the complete NLP enrichment pipeline synchronously.
    Used for the fast path (native PDFs) and as a Celery-unavailable fallback.
    """
    if not text:
        log_ingestion(docket_id, "error", "Text extraction yielded empty result.")
        return

    # --- Legal NER (replaces regex-only extraction) ---
    entities = extract_legal_entities(text)
    plaintiff = entities["plaintiff"]
    defendant = entities["defendant"]

    # Fallback to case_name parsing if NER found nothing
    if (not plaintiff or not defendant) and " v. " in case_name:
        parts = case_name.split(" v. ", 1)
        if not plaintiff:
            plaintiff = parts[0].strip()
        if not defendant:
            defendant = parts[1].strip()

    logger.info("  Plaintiff : %s", plaintiff or "(not found)")
    logger.info("  Defendant : %s", defendant or "(not found)")
    logger.info("  Statutes  : %s", ", ".join(entities["statutes"][:3]) or "(none)")
    logger.info("  Damages   : %s", ", ".join(entities["damages"][:3]) or "(none)")

    # --- Summarization (distilBART, ~14 s CPU) ---
    summary = generate_summary(text, max_input_chars=settings.SUMMARY_MAX_CHARS)
    logger.info("  Summary   : %s", summary[:120] + ("…" if len(summary) > 120 else ""))

    # --- Case type classification (Bloomberg Law parity) ---
    classification = classify_case(summary or text[:1024])
    logger.info(
        "  Case type : %s (%.0f%% confidence, method=%s)",
        classification["primary_type"],
        classification["confidence"] * 100,
        classification["method"],
    )

    # --- Sentence embedding + precedent similarity ---
    embedding = generate_embedding(summary or text[:2000])
    similar_cases = find_similar_filings(embedding, top_k=5) if embedding else []
    top_similarity = similar_cases[0]["score"] if similar_cases else 0.0
    logger.info("  Precedents: %d similar cases found.", len(similar_cases))

    # --- Risk scoring ---
    risk = score_filing(
        case_type=classification["primary_type"],
        court=court,
        damages=entities["damages"],
        statutes=entities["statutes"],
        precedent_similarity=top_similarity,
        similar_cases=similar_cases,
    )
    logger.info("  Risk score: %d/10 — %s", risk["score"], risk["predicted_outcome"][:80])

    # --- Persist full intelligence record ---
    save_filing(
        docket_id=docket_id,
        court=court,
        court_name=court_name,
        court_full_name=court_full_name,
        court_citation=court_citation,
        case_name=case_name,
        plaintiff=plaintiff,
        defendant=defendant,
        summary=summary,
        pdf_path=pdf_path,
        date_filed=date_filed,
        case_type=classification["primary_type"],
        case_type_confidence=classification["confidence"],
        allegations=entities["damages"] + entities["statutes"],
        statutes=entities["statutes"],
        damages=entities["damages"],
        risk_score=risk["score"],
        risk_breakdown=risk["breakdown"],
        predicted_outcome=risk["predicted_outcome"],
        embedding=embedding,
        similar_cases=similar_cases,
        processing_status="complete",
    )
    log_ingestion(docket_id, "success", f"Processed: {case_name}")
    logger.info("  ✓ Saved to database.")


def run_poll_cycle(client: CourtListenerClient) -> None:
    """Run one poll cycle: detect new dockets and process each one."""
    logger.info("Polling CourtListener for new %s dockets…", settings.TARGET_COURT)
    dockets = client.fetch_recent_dockets(
        court=settings.TARGET_COURT,
        since_minutes=10080,  # 1 week back
    )
    logger.info("Found %d docket(s).", len(dockets))
    for docket in dockets:
        try:
            process_docket(client, docket)
        except Exception as exc:
            docket_id = str(docket.get("id", "unknown"))
            logger.exception("Unhandled error processing docket %s: %s", docket_id, exc)
            log_ingestion(docket_id, "error", str(exc))


def main():
    client = CourtListenerClient(
        base_url=settings.COURTLISTENER_BASE_URL,
        api_token=settings.COURTLISTENER_API_TOKEN,
    )

    interval = settings.POLL_INTERVAL_SECONDS
    if interval == 0:
        logger.info("POLL_INTERVAL_SECONDS=0 — running once and exiting.")
        run_poll_cycle(client)
        return

    logger.info("Starting poller. Interval: %d seconds.", interval)
    while True:
        try:
            run_poll_cycle(client)
        except Exception as exc:
            logger.exception("Poll cycle failed: %s", exc)
        logger.info("Sleeping %d seconds until next poll…", interval)
        time.sleep(interval)


if __name__ == "__main__":
    main()
