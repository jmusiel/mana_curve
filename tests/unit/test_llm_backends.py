"""Tests for LLM backend abstraction."""

import json
from unittest.mock import MagicMock, patch

import pytest

from auto_goldfish.autocard.llm_backends import (
    GeminiBackend,
    OllamaBackend,
    create_backend,
)


class TestGeminiRetryDelay:
    def test_parses_retry_delay_from_error(self):
        msg = "Please retry in 44.28441972s."
        assert GeminiBackend._parse_retry_delay(msg) == pytest.approx(45.28, abs=0.01)

    def test_default_when_no_match(self):
        assert GeminiBackend._parse_retry_delay("some other error") == 60.0


class TestOllamaBackend:
    @patch("auto_goldfish.autocard.llm_backends.OllamaBackend.chat")
    def test_chat_returns_string(self, mock_chat):
        mock_chat.return_value = '{"categories": []}'
        backend = OllamaBackend(model="test-model")
        result = backend.chat(system="sys", user="usr")
        assert result == '{"categories": []}'

    def test_repr(self):
        backend = OllamaBackend(model="gemma3:12b")
        assert "gemma3:12b" in repr(backend)


class TestGeminiBackend:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            GeminiBackend()

    def test_empty_api_key_raises(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "  ")
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            GeminiBackend()

    def test_chat_calls_api(self, monkeypatch):
        genai = pytest.importorskip("google.genai")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"categories": [], "metadata": {}}'
        mock_client.models.generate_content.return_value = mock_response

        monkeypatch.setattr(genai, "Client", lambda **kw: mock_client)

        backend = GeminiBackend(model="gemini-2.0-flash")
        result = backend.chat(
            system="You are a labeler",
            user="Label this card",
            json_schema={"type": "object"},
        )

        assert json.loads(result) == {"categories": [], "metadata": {}}
        mock_client.models.generate_content.assert_called_once()

        # Verify config includes JSON schema and temperature
        call_kwargs = mock_client.models.generate_content.call_args[1]
        config = call_kwargs["config"]
        assert config.response_mime_type == "application/json"
        assert config.temperature == 0

    def test_chat_without_schema(self, monkeypatch):
        genai = pytest.importorskip("google.genai")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"categories": []}'
        mock_client.models.generate_content.return_value = mock_response

        monkeypatch.setattr(genai, "Client", lambda **kw: mock_client)

        backend = GeminiBackend(model="gemini-2.0-flash")
        backend.chat(system="sys", user="usr", json_schema=None)

        # Without schema, response_mime_type should not be set
        call_kwargs = mock_client.models.generate_content.call_args[1]
        config = call_kwargs["config"]
        assert config.response_mime_type is None

    def test_rate_limit_retry(self, monkeypatch):
        genai = pytest.importorskip("google.genai")
        from google.genai import errors as genai_errors
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")

        mock_client = MagicMock()
        monkeypatch.setattr(genai, "Client", lambda **kw: mock_client)

        # First call raises 429, second succeeds
        mock_response = MagicMock()
        mock_response.text = '{"categories": []}'
        rate_error = genai_errors.ClientError(429, {"error": {"message": "429 RESOURCE_EXHAUSTED. Please retry in 1s."}})
        mock_client.models.generate_content.side_effect = [rate_error, mock_response]

        backend = GeminiBackend(model="gemini-2.0-flash", rate_limit=True)
        monkeypatch.setattr("time.sleep", lambda _: None)  # skip actual sleep
        result = backend.chat(system="sys", user="usr")
        assert result == '{"categories": []}'
        assert mock_client.models.generate_content.call_count == 2

    def test_429_without_rate_limit_raises(self, monkeypatch):
        genai = pytest.importorskip("google.genai")
        from google.genai import errors as genai_errors
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")

        mock_client = MagicMock()
        monkeypatch.setattr(genai, "Client", lambda **kw: mock_client)

        rate_error = genai_errors.ClientError(429, {"error": {"message": "429 RESOURCE_EXHAUSTED"}})
        mock_client.models.generate_content.side_effect = rate_error

        backend = GeminiBackend(model="gemini-2.0-flash", rate_limit=False)
        with pytest.raises(genai_errors.ClientError):
            backend.chat(system="sys", user="usr")

    def test_repr(self, monkeypatch):
        genai = pytest.importorskip("google.genai")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setattr(genai, "Client", lambda **kw: MagicMock())
        backend = GeminiBackend(model="gemini-2.0-flash")
        assert "gemini-2.0-flash" in repr(backend)

    def test_repr_rate_limit(self, monkeypatch):
        genai = pytest.importorskip("google.genai")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setattr(genai, "Client", lambda **kw: MagicMock())
        backend = GeminiBackend(model="gemini-2.0-flash", rate_limit=True)
        assert "rate_limit=True" in repr(backend)


class TestCreateBackend:
    def test_create_ollama(self):
        backend = create_backend("ollama", model="gemma3:12b")
        assert isinstance(backend, OllamaBackend)
        assert backend.model == "gemma3:12b"

    def test_create_ollama_default_model(self):
        backend = create_backend("ollama")
        assert backend.model == "llama4:16x17b"

    def test_create_gemini(self, monkeypatch):
        genai = pytest.importorskip("google.genai")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setattr(genai, "Client", lambda **kw: MagicMock())
        backend = create_backend("gemini")
        assert isinstance(backend, GeminiBackend)
        assert backend.model == "gemini-2.0-flash"

    def test_create_gemini_custom_model(self, monkeypatch):
        genai = pytest.importorskip("google.genai")
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setattr(genai, "Client", lambda **kw: MagicMock())
        backend = create_backend("gemini", model="gemini-1.5-pro")
        assert backend.model == "gemini-1.5-pro"

    def test_create_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown API backend"):
            create_backend("openai")
