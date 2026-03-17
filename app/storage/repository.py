"""
Repository layer: thin wrapper around ORM queries for use by the pipeline.

Keeps pipeline code free of direct Django ORM calls, making it
straightforward to test with a fake repository in unit tests.
"""
import json
import logging

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
    # NLP intelligence fields (all optional — pipeline sets them after ingestion)
    case_type: str = "",
    case_type_confidence: float = None,
    allegations: list = None,
    statutes: list = None,
    damages: list = None,
    risk_score: int = None,
    risk_breakdown: dict = None,
    predicted_outcome: str = "",
    embedding: list = None,
    similar_cases: list = None,
    processing_status: str = "pending",
) -> "Filing":
    """
    Upsert a filing record.
    Creates a new record or updates existing one (idempotent).
    All NLP fields are optional so the record can be saved immediately on
    ingestion and enriched later by async Celery tasks.
    """
    from app.storage.models import Filing

    defaults = dict(
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
        processing_status=processing_status,
    )

    # NLP fields — only include if provided to avoid overwriting enriched data
    if case_type:
        defaults["case_type"] = case_type
    if case_type_confidence is not None:
        defaults["case_type_confidence"] = case_type_confidence
    if allegations is not None:
        defaults["allegations"] = json.dumps(allegations)
    if statutes is not None:
        defaults["statutes"] = json.dumps(statutes)
    if damages is not None:
        defaults["damages"] = json.dumps(damages)
    if risk_score is not None:
        defaults["risk_score"] = risk_score
    if risk_breakdown is not None:
        defaults["risk_breakdown"] = json.dumps(risk_breakdown)
    if predicted_outcome:
        defaults["predicted_outcome"] = predicted_outcome
    if embedding is not None:
        defaults["embedding_json"] = json.dumps(embedding)
    if similar_cases is not None:
        defaults["similar_cases_json"] = json.dumps(similar_cases)

    filing, created = Filing.objects.update_or_create(
        docket_id=docket_id,
        defaults=defaults,
    )
    action = "Created" if created else "Updated"
    logger.info("%s filing: %s (%s)", action, case_name, docket_id)
    return filing


def log_ingestion(docket_id: str, status: str, message: str = "") -> None:
    """Append an IngestionLog entry."""
    from app.storage.models import IngestionLog
    IngestionLog.objects.create(docket_id=docket_id, status=status, message=message)
