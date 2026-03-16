"""
Tests for app/ingestion/courtlistener.py

All HTTP calls are mocked — no network required.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from requests.exceptions import HTTPError, ConnectionError

from app.ingestion.courtlistener import CourtListenerClient


@pytest.fixture
def client():
    return CourtListenerClient(base_url="https://example.com/api/rest/v3", api_token="test-token")


class TestInit:
    def test_sets_auth_header(self, client):
        assert client.session.headers["Authorization"] == "Token test-token"

    def test_no_auth_header_when_empty_token(self):
        c = CourtListenerClient(base_url="https://example.com", api_token="")
        assert "Authorization" not in c.session.headers

    def test_strips_trailing_slash_from_base_url(self, client):
        assert not client.base_url.endswith("/")


class TestFetchRecentDockets:
    def test_returns_results_list(self, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": [{"id": "1"}, {"id": "2"}]}
        mock_resp.raise_for_status = MagicMock()

        client.session.get = MagicMock(return_value=mock_resp)
        results = client.fetch_recent_dockets("nysd")

        assert len(results) == 2
        assert results[0]["id"] == "1"

    def test_returns_empty_list_on_request_error(self, client):
        client.session.get = MagicMock(side_effect=ConnectionError("timeout"))
        results = client.fetch_recent_dockets("nysd")
        assert results == []

    def test_passes_court_and_date_params(self, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        client.fetch_recent_dockets("nysd", since_minutes=60)

        _, kwargs = client.session.get.call_args
        params = kwargs["params"]
        assert params["court"] == "nysd"
        assert "date_filed__gte" in params


class TestFetchCourtWithCache:
    def test_fetches_court_and_caches(self, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"short_name": "S.D.N.Y.", "full_name": "Southern District"}
        mock_resp.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_resp)

        result1 = client.fetch_court("nysd")
        result2 = client.fetch_court("nysd")

        assert result1["short_name"] == "S.D.N.Y."
        assert client.session.get.call_count == 1  # second call served from cache
        assert result1 is result2

    def test_returns_none_on_error(self, client):
        client.session.get = MagicMock(side_effect=ConnectionError("network down"))
        result = client.fetch_court("nysd")
        assert result is None

    def test_different_courts_fetched_separately(self, client):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = [
            {"short_name": "S.D.N.Y."},
            {"short_name": "N.D.Cal."},
        ]
        client.session.get = MagicMock(return_value=mock_resp)

        client.fetch_court("nysd")
        client.fetch_court("cand")

        assert client.session.get.call_count == 2


class TestDownloadPdf:
    def test_writes_file_on_success(self, client, tmp_path):
        dest = str(tmp_path / "filing.pdf")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_content.return_value = [b"PDF data chunk"]
        client.session.get = MagicMock(return_value=mock_resp)

        success = client.download_pdf("https://example.com/filing.pdf", dest)

        assert success is True
        assert open(dest, "rb").read() == b"PDF data chunk"

    def test_returns_false_on_http_error(self, client, tmp_path):
        dest = str(tmp_path / "filing.pdf")
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = HTTPError("404")
        client.session.get = MagicMock(return_value=mock_resp)

        success = client.download_pdf("https://example.com/missing.pdf", dest)

        assert success is False
