from django.db import models


class Filing(models.Model):
    """
    Stores structured intelligence extracted from a court filing.

    New fields (v3 schema):
      - case_type / case_type_confidence: Bloomberg Law-parity case tagging
      - risk_score / risk_breakdown:      1–10 litigation risk score
      - allegations:                      key allegations JSON array
      - statutes / damages:               extracted legal entities
      - embedding_json:                   384-dim sentence embedding (pgvector upgrade path)
      - processing_status:                async pipeline state machine
      - predicted_outcome:                plain-English outcome prediction
      - similar_cases_json:               top-5 precedent matches
    """

    PROCESSING_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("ocr_queued", "OCR Queued"),
        ("processing", "Processing"),
        ("complete", "Complete"),
        ("error", "Error"),
    ]

    # --- Core identification ---
    docket_id = models.CharField(max_length=128, unique=True, db_index=True)
    court = models.CharField(max_length=64)
    court_name = models.CharField(max_length=256, blank=True)
    court_full_name = models.CharField(max_length=512, blank=True)
    court_citation = models.CharField(max_length=64, blank=True)
    case_name = models.CharField(max_length=512)
    date_filed = models.DateField(null=True, blank=True)

    # --- Parties ---
    plaintiff = models.CharField(max_length=256, blank=True)
    defendant = models.CharField(max_length=256, blank=True)

    # --- NLP outputs ---
    summary = models.TextField(blank=True)
    # Bloomberg Law-parity case type classification
    case_type = models.CharField(max_length=128, blank=True, db_index=True)
    case_type_confidence = models.FloatField(null=True, blank=True)
    # Key allegations extracted by legal NER (JSON array of strings)
    allegations = models.TextField(blank=True)
    # Statute citations extracted (JSON array of strings)
    statutes = models.TextField(blank=True)
    # Damage strings extracted (JSON array of strings)
    damages = models.TextField(blank=True)

    # --- Risk intelligence ---
    risk_score = models.IntegerField(null=True, blank=True, db_index=True)
    risk_breakdown = models.TextField(blank=True)   # JSON dict
    predicted_outcome = models.TextField(blank=True)

    # --- Precedent matching ---
    # 384-dim float array serialised as JSON.
    # Upgrade path: ALTER TABLE ADD COLUMN embedding vector(384);
    embedding_json = models.TextField(blank=True)
    similar_cases_json = models.TextField(blank=True)  # JSON array of top-k matches

    # --- Storage ---
    pdf_path = models.CharField(max_length=512, blank=True)
    processing_status = models.CharField(
        max_length=16,
        choices=PROCESSING_STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Filing"
        verbose_name_plural = "Filings"

    def __str__(self):
        return f"{self.case_name} ({self.court})"


class IngestionLog(models.Model):
    """
    Tracks every polling attempt and records errors for reliability auditing.
    """
    STATUS_CHOICES = [
        ("success", "Success"),
        ("error", "Error"),
        ("skipped", "Skipped (duplicate)"),
    ]
    docket_id = models.CharField(max_length=128, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.docket_id} — {self.status} @ {self.created_at}"
