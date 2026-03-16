"""
Tests for app/api/views.py

Uses Django's test client with an in-memory SQLite database.
"""
import pytest
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from app.storage.models import Filing, IngestionLog


def make_filing(**kwargs):
    defaults = dict(
        docket_id="12345",
        court="nysd",
        court_name="S.D.N.Y.",
        court_full_name="District Court, Southern District of New York",
        court_citation="S.D.N.Y.",
        case_name="Smith v. Acme Corp",
        plaintiff="John Smith",
        defendant="Acme Corp",
        summary="Plaintiff alleges breach of contract.",
        date_filed="2024-01-15",
    )
    defaults.update(kwargs)
    return Filing.objects.create(**defaults)


class TestLatestFilingsView(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_200(self):
        response = self.client.get("/api/filings/latest/")
        assert response.status_code == 200

    def test_returns_empty_list_when_no_filings(self):
        response = self.client.get("/api/filings/latest/")
        assert response.json() == []

    def test_returns_filing_fields(self):
        make_filing()
        response = self.client.get("/api/filings/latest/")
        data = response.json()
        assert len(data) == 1
        filing = data[0]
        assert filing["docket_id"] == "12345"
        assert filing["court"] == "nysd"
        assert filing["court_name"] == "S.D.N.Y."
        assert filing["court_full_name"] == "District Court, Southern District of New York"
        assert filing["court_citation"] == "S.D.N.Y."
        assert filing["plaintiff"] == "John Smith"
        assert filing["defendant"] == "Acme Corp"

    def test_limit_param_respected(self):
        for i in range(5):
            make_filing(docket_id=str(i))
        response = self.client.get("/api/filings/latest/?limit=3")
        assert len(response.json()) == 3

    def test_limit_capped_at_100(self):
        for i in range(5):
            make_filing(docket_id=str(i))
        response = self.client.get("/api/filings/latest/?limit=999")
        # Should not raise; returns all 5 (capped at 100 server-side)
        assert len(response.json()) == 5

    def test_most_recent_first(self):
        make_filing(docket_id="older", case_name="Old Case v. Defendant")
        make_filing(docket_id="newer", case_name="New Case v. Defendant")
        data = self.client.get("/api/filings/latest/").json()
        assert data[0]["docket_id"] == "newer"


class TestFilingDetailView(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_filing_by_docket_id(self):
        make_filing(docket_id="ABC-001")
        response = self.client.get("/api/filings/ABC-001/")
        assert response.status_code == 200
        assert response.json()["docket_id"] == "ABC-001"

    def test_returns_404_for_unknown_docket(self):
        response = self.client.get("/api/filings/NONEXISTENT/")
        assert response.status_code == 404

    def test_404_response_has_detail_key(self):
        response = self.client.get("/api/filings/NONEXISTENT/")
        assert "detail" in response.json()


class TestIngestionLogsView(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_200(self):
        response = self.client.get("/api/ingestion/logs/")
        assert response.status_code == 200

    def test_returns_log_entries(self):
        IngestionLog.objects.create(docket_id="1", status="success", message="ok")
        IngestionLog.objects.create(docket_id="2", status="error", message="bad pdf")
        data = self.client.get("/api/ingestion/logs/").json()
        assert len(data) == 2
        statuses = {entry["status"] for entry in data}
        assert statuses == {"success", "error"}

    def test_log_fields_present(self):
        IngestionLog.objects.create(docket_id="99", status="skipped", message="duplicate")
        entry = self.client.get("/api/ingestion/logs/").json()[0]
        assert entry["docket_id"] == "99"
        assert entry["status"] == "skipped"
        assert entry["message"] == "duplicate"


class TestHealthCheckView(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_200(self):
        response = self.client.get("/api/health/")
        assert response.status_code == 200

    def test_returns_ok_status(self):
        data = self.client.get("/api/health/").json()
        assert data["status"] == "ok"

    def test_reports_filing_count(self):
        make_filing(docket_id="x1")
        make_filing(docket_id="x2")
        data = self.client.get("/api/health/").json()
        assert data["filings_in_db"] == 2
