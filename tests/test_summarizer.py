"""
Tests for app/summarization/summarizer.py

The HuggingFace pipeline is always mocked — no model download required.
"""
import pytest
from unittest.mock import MagicMock, patch
import app.summarization.summarizer as summarizer_module
from app.summarization.summarizer import generate_summary


@pytest.fixture(autouse=True)
def reset_pipeline():
    """Reset the module-level pipeline cache between tests."""
    original = summarizer_module._pipeline
    summarizer_module._pipeline = None
    yield
    summarizer_module._pipeline = original


def _make_pipeline(summary_text="A concise summary."):
    mock_pipe = MagicMock()
    mock_pipe.return_value = [{"summary_text": summary_text}]
    return mock_pipe


class TestGenerateSummary:
    def test_returns_summary_string(self):
        mock_pipe = _make_pipeline("Plaintiff alleges breach of contract.")
        with patch("app.summarization.summarizer._get_pipeline", return_value=mock_pipe):
            result = generate_summary("Some long filing text here.")
        assert result == "Plaintiff alleges breach of contract."

    def test_truncates_input_to_max_chars(self):
        mock_pipe = _make_pipeline("Summary.")
        long_text = "X" * 5000

        with patch("app.summarization.summarizer._get_pipeline", return_value=mock_pipe):
            generate_summary(long_text, max_input_chars=2000)

        called_text = mock_pipe.call_args[0][0]
        assert len(called_text) == 2000

    def test_returns_empty_for_empty_input(self):
        mock_pipe = _make_pipeline()
        with patch("app.summarization.summarizer._get_pipeline", return_value=mock_pipe):
            assert generate_summary("") == ""
            assert generate_summary("   ") == ""
        mock_pipe.assert_not_called()

    def test_returns_empty_when_pipeline_unavailable(self):
        with patch("app.summarization.summarizer._get_pipeline", return_value=None):
            result = generate_summary("Some filing text.")
        assert result == ""

    def test_returns_empty_on_pipeline_exception(self):
        mock_pipe = MagicMock(side_effect=RuntimeError("CUDA out of memory"))
        with patch("app.summarization.summarizer._get_pipeline", return_value=mock_pipe):
            result = generate_summary("Some text.")
        assert result == ""

    def test_pipeline_loaded_lazily_and_cached(self):
        mock_pipe = _make_pipeline("Summary.")
        mock_transformers = MagicMock()
        mock_transformers.pipeline.return_value = mock_pipe

        with patch.dict("sys.modules", {"transformers": mock_transformers}):
            summarizer_module._pipeline = None
            pipe1 = summarizer_module._get_pipeline()
            pipe2 = summarizer_module._get_pipeline()

        assert mock_transformers.pipeline.call_count == 1
        assert pipe1 is pipe2
