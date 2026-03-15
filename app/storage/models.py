from django.db import models


class Filing(models.Model):
    """
    Stores structured intelligence extracted from a court filing.
    """
    docket_id = models.CharField(max_length=128, unique=True, db_index=True)
    court = models.CharField(max_length=64)
    court_name = models.CharField(max_length=256, blank=True)       # short_name, e.g. "District of Columbia"
    court_full_name = models.CharField(max_length=512, blank=True)  # full_name, e.g. "District Court, District of Columbia"
    court_citation = models.CharField(max_length=64, blank=True)    # citation_string, e.g. "D.D.C."
    case_name = models.CharField(max_length=512)
    plaintiff = models.CharField(max_length=256, blank=True)
    defendant = models.CharField(max_length=256, blank=True)
    summary = models.TextField(blank=True)
    pdf_path = models.CharField(max_length=512, blank=True)
    date_filed = models.DateField(null=True, blank=True)
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
