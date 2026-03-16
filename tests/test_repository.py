"""
Tests for app/storage/repository.py

Uses Django's TestCase with in-memory SQLite.
"""
from django.test import TestCase
from app.storage.models import Filing, IngestionLog
from app.storage import repository


class TestFilingExists(TestCase):
    def test_returns_false_when_no_filing(self):
        assert repository.filing_exists("NONEXISTENT") is False

    def test_returns_true_when_filing_present(self):
        Filing.objects.create(docket_id="EXISTING", court="nysd", case_name="A v. B")
        assert repository.filing_exists("EXISTING") is True


class TestSaveFiling(TestCase):
    def _save(self, **kwargs):
        defaults = dict(
            docket_id="D001",
            court="nysd",
            case_name="Smith v. Jones",
            plaintiff="Smith",
            defendant="Jones",
            summary="A summary.",
            pdf_path="/data/D001.pdf",
        )
        defaults.update(kwargs)
        return repository.save_filing(**defaults)

    def test_creates_new_filing(self):
        filing = self._save()
        assert Filing.objects.filter(docket_id="D001").exists()
        assert filing.case_name == "Smith v. Jones"

    def test_returns_filing_object(self):
        filing = self._save()
        assert isinstance(filing, Filing)

    def test_updates_existing_filing(self):
        self._save(summary="Old summary.")
        self._save(summary="New summary.")
        assert Filing.objects.filter(docket_id="D001").count() == 1
        assert Filing.objects.get(docket_id="D001").summary == "New summary."

    def test_saves_court_metadata(self):
        self._save(
            court_name="S.D.N.Y.",
            court_full_name="District Court, Southern District of New York",
            court_citation="S.D.N.Y.",
        )
        filing = Filing.objects.get(docket_id="D001")
        assert filing.court_name == "S.D.N.Y."
        assert filing.court_full_name == "District Court, Southern District of New York"
        assert filing.court_citation == "S.D.N.Y."

    def test_saves_date_filed(self):
        from datetime import date
        self._save(date_filed=date(2024, 1, 15))
        assert Filing.objects.get(docket_id="D001").date_filed == date(2024, 1, 15)

    def test_accepts_none_date_filed(self):
        self._save(date_filed=None)
        assert Filing.objects.get(docket_id="D001").date_filed is None


class TestLogIngestion(TestCase):
    def test_creates_log_entry(self):
        repository.log_ingestion("D001", "success", "Saved OK")
        log = IngestionLog.objects.get(docket_id="D001")
        assert log.status == "success"
        assert log.message == "Saved OK"

    def test_creates_multiple_logs_for_same_docket(self):
        repository.log_ingestion("D001", "error", "First attempt failed")
        repository.log_ingestion("D001", "success", "Second attempt ok")
        assert IngestionLog.objects.filter(docket_id="D001").count() == 2

    def test_empty_message_allowed(self):
        repository.log_ingestion("D002", "skipped")
        log = IngestionLog.objects.get(docket_id="D002")
        assert log.message == ""
