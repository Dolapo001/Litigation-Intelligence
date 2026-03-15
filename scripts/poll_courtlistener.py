#!/usr/bin/env python
"""
Litigation Intelligence — Court Filing Poller
=============================================

A standalone worker script that:
  1. Polls CourtListener for new SDNY dockets.
  2. Downloads the associated complaint PDF.
  3. Extracts text (native PDF → OCR fallback).
  4. Extracts plaintiff/defendant entities.
  5. Generates a short AI summary.
  6. Persists everything to PostgreSQL via Django ORM.

Run this script independently of the Django dev server:
    python scripts/poll_courtlistener.py

Set POLL_INTERVAL_SECONDS=0 to run once (useful for CI / testing).
"""
import os
import sys
import time
import logging
from pathlib import Path

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
from app.processing.pdf_extractor import extract_text
from app.extraction.entities import extract_entities
from app.summarization.summarizer import generate_summary
from app.storage.repository import filing_exists, save_filing, log_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("poller")


def process_docket(client: CourtListenerClient, docket: dict) -> None:
    """
    Full pipeline for a single newly detected docket.
    """
    docket_id = str(docket["id"])
    case_name = docket.get("case_name", "Unknown v. Unknown")
    
    # Extract court code from URL if necessary
    court_raw = docket.get("court", settings.TARGET_COURT)
    if court_raw and "/courts/" in str(court_raw):
        # Extract 'dcd' from '.../courts/dcd/?format=json'
        court = str(court_raw).split("/courts/")[-1].split("/")[0]
    else:
        court = court_raw or settings.TARGET_COURT

    date_filed = docket.get("date_filed")

    logger.info("─" * 60)
    logger.info("New Filing Detected")
    logger.info("  Court    : %s", court)
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

    # --- Extract text ---
    text = extract_text(str(pdf_path), min_length=settings.PDF_TEXT_MIN_LENGTH)
    if not text:
        log_ingestion(docket_id, "error", "Text extraction yielded empty result.")
        return

    # --- Extract entities ---
    entities = extract_entities(text)
    plaintiff = entities["plaintiff"]
    defendant = entities["defendant"]

    # Fallback to parsing case_name if extraction failed
    if (not plaintiff or not defendant) and " v. " in case_name:
        parts = case_name.split(" v. ", 1)
        if not plaintiff:
            plaintiff = parts[0].strip()
        if not defendant:
            defendant = parts[1].strip()

    logger.info("  Plaintiff: %s", plaintiff or "(not found)")
    logger.info("  Defendant: %s", defendant or "(not found)")

    # --- Generate summary ---
    summary = generate_summary(text, max_input_chars=settings.SUMMARY_MAX_CHARS)
    logger.info("  Summary  : %s", summary[:120] + ("…" if len(summary) > 120 else ""))

    # --- Persist ---
    save_filing(
        docket_id=docket_id,
        court=court,
        case_name=case_name,
        plaintiff=plaintiff,
        defendant=defendant,
        summary=summary,
        pdf_path=str(pdf_path),
        date_filed=date_filed,
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
