"""
Repository layer: thin wrapper around ORM queries for use by the pipeline.

Keeps pipeline code free of direct Django ORM calls, making it
straightforward to test with a fake repository in unit tests.
"""
import logging
import os

logger = logging.getLogger(__name__)


def filing_exists(docket_id: str) -> bool:
    """Return True if a filing with this docket_id is already in the database."""
    from app.storage.models import Filing
    return Filing.objects.filter(docket_id=docket_id).exists()


def save_filing(
    docket_id: str,
    court: str,
    case_name: str,
    plaintiff: str,
    defendant: str,
    summary: str,
    pdf_path: str,
    date_filed=None,
    court_name: str = "",
    court_full_name: str = "",
    court_citation: str = "",
) -> "Filing":
    """
    Upsert a filing record.
    Creates a new record or updates existing one (idempotent).
    """
    from app.storage.models import Filing

    filing, created = Filing.objects.update_or_create(
        docket_id=docket_id,
        defaults=dict(
            court=court,
            court_name=court_name,
            court_full_name=court_full_name,
            court_citation=court_citation,
            case_name=case_name,
            plaintiff=plaintiff,
            defendant=defendant,
            summary=summary,
            pdf_path=str(pdf_path),
            date_filed=date_filed,
        ),
    )
    action = "Created" if created else "Updated"
    logger.info("%s filing: %s (%s)", action, case_name, docket_id)
    return filing


def log_ingestion(docket_id: str, status: str, message: str = "") -> None:
    """Append an IngestionLog entry."""
    from app.storage.models import IngestionLog
    IngestionLog.objects.create(docket_id=docket_id, status=status, message=message)
