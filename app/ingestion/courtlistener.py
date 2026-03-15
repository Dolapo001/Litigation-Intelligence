"""
CourtListener API client.

Wraps the CourtListener REST API v3 to poll for new dockets
and retrieve associated docket entries and RECAP documents.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class CourtListenerClient:
    """Thin wrapper around the CourtListener REST API."""

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        if api_token:
            self.session.headers["Authorization"] = f"Token {api_token}"
        self.session.headers["User-Agent"] = "LitigationIntelligencePrototype/1.0"

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_recent_dockets(self, court: str, since_minutes: int = 10) -> list[dict]:
        """
        Return dockets filed in the last `since_minutes` for the given court.
        Uses date_filed__gte filter to avoid re-fetching old cases.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        cutoff_str = cutoff.strftime("%Y-%m-%d")  # CourtListener accepts date only
        params = {
            "court": court,
            "date_filed__gte": cutoff_str,
            "order_by": "-date_filed",
            "format": "json",
        }
        try:
            data = self._get("/dockets/", params)
            return data.get("results", [])
        except requests.RequestException as exc:
            logger.error("Failed to fetch dockets from CourtListener: %s", exc)
            return []

    def fetch_docket_entries(self, docket_id: str) -> list[dict]:
        """Return all docket entries for a given docket."""
        params = {"docket": docket_id, "format": "json"}
        try:
            data = self._get("/docket-entries/", params)
            return data.get("results", [])
        except requests.RequestException as exc:
            logger.error("Failed to fetch docket entries for %s: %s", docket_id, exc)
            return []

    def fetch_recap_document(self, document_id: str) -> Optional[dict]:
        """Return metadata for a single RECAP document."""
        try:
            return self._get(f"/recap-documents/{document_id}/")
        except requests.RequestException as exc:
            logger.error("Failed to fetch RECAP document %s: %s", document_id, exc)
            return None

    def download_pdf(self, pdf_url: str, dest_path: str) -> bool:
        """
        Download a PDF from CourtListener's RECAP archive to `dest_path`.
        Returns True on success.
        """
        try:
            resp = self.session.get(pdf_url, timeout=60, stream=True)
            resp.raise_for_status()
            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    fh.write(chunk)
            logger.info("Downloaded PDF to %s", dest_path)
            return True
        except (requests.RequestException, OSError) as exc:
            logger.error("Failed to download PDF from %s: %s", pdf_url, exc)
            return False
