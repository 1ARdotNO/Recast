"""Tests for Stage 4 — LLM Context Pass."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from recast.pipeline.stages.llm_pass import (
    llm_pass, _parse_llm_response, _format_transcript_for_prompt,
    _load_prompt_template,
)


SAMPLE_TRANSCRIPT = {
    "language": "no",
    "segments": [
        {"start": 0.0, "end": 5.0, "text": "Velkommen til sendingen."},
        {"start": 5.0, "end": 12.0, "text": "Nå skal vi høre på Karusell av Postgirobygget."},
        {"start": 12.0, "end": 20.0, "text": "I dag snakker vi om politikk."},
    ],
}


class TestFormatTranscript:
    def test_basic(self):
        text = _format_transcript_for_prompt(SAMPLE_TRANSCRIPT)
        assert "[0.0s - 5.0s]" in text
        assert "Velkommen" in text
        assert "[5.0s - 12.0s]" in text

    def test_empty(self):
        text = _format_transcript_for_prompt({"segments": []})
        assert text == ""


class TestParseResponse:
    def test_valid_json(self):
        response = '[{"start": 5.0, "end": 12.0, "reason": "song intro", "confidence": 0.9}]'
        result = _parse_llm_response(response)
        assert len(result) == 1
        assert result[0]["start"] == 5.0

    def test_json_with_surrounding_text(self):
        response = 'Here are the cuts:\n[{"start": 5.0, "end": 12.0, "reason": "song intro", "confidence": 0.9}]\nDone.'
        result = _parse_llm_response(response)
        assert len(result) == 1

    def test_empty_array(self):
        result = _parse_llm_response("[]")
        assert result == []

    def test_no_json(self):
        result = _parse_llm_response("No segments to remove.")
        assert result == []

    def test_invalid_json(self):
        result = _parse_llm_response("[{invalid json}]")
        assert result == []


class TestLoadPromptTemplate:
    def test_default(self):
        template = _load_prompt_template()
        assert "{transcript}" in template
        assert "Remove:" in template

    def test_custom(self, tmp_path):
        custom = tmp_path / "custom_prompt.txt"
        custom.write_text("Custom prompt: {transcript}")
        template = _load_prompt_template(str(custom))
        assert "Custom prompt:" in template

    def test_missing_custom_falls_back(self):
        template = _load_prompt_template("/nonexistent/prompt.txt")
        assert "{transcript}" in template


class TestLLMPass:
    @pytest.fixture
    def mock_ollama(self):
        with patch("ollama.Client") as MockClient:
            client_instance = MagicMock()
            MockClient.return_value = client_instance

            client_instance.chat.return_value = {
                "message": {
                    "content": json.dumps([
                        {
                            "start": 5.0,
                            "end": 12.0,
                            "reason": "song introduction",
                            "confidence": 0.9,
                        },
                    ]),
                },
            }
            yield client_instance

    def test_basic(self, tmp_path, mock_ollama):
        output_dir = tmp_path / "job"
        cuts = llm_pass(SAMPLE_TRANSCRIPT, output_dir)
        assert len(cuts) == 1
        assert cuts[0]["start"] == 5.0
        assert cuts[0]["reason"] == "song introduction"

    def test_output_file(self, tmp_path, mock_ollama):
        output_dir = tmp_path / "job"
        llm_pass(SAMPLE_TRANSCRIPT, output_dir)
        assert (output_dir / "cuts_llm.json").exists()

    def test_confidence_filtering(self, tmp_path):
        with patch("ollama.Client") as MockClient:
            client = MagicMock()
            MockClient.return_value = client
            client.chat.return_value = {
                "message": {
                    "content": json.dumps([
                        {"start": 5.0, "end": 8.0, "reason": "ad", "confidence": 0.3},
                        {"start": 10.0, "end": 12.0, "reason": "jingle", "confidence": 0.8},
                    ]),
                },
            }
            output_dir = tmp_path / "job"
            cuts = llm_pass(
                SAMPLE_TRANSCRIPT, output_dir, confidence_threshold=0.6,
            )
            assert len(cuts) == 1
            assert cuts[0]["start"] == 10.0

    def test_model_passed_correctly(self, tmp_path, mock_ollama):
        output_dir = tmp_path / "job"
        llm_pass(
            SAMPLE_TRANSCRIPT, output_dir,
            ollama_model="llama3.2:3b",
        )
        call_kwargs = mock_ollama.chat.call_args[1]
        assert call_kwargs["model"] == "llama3.2:3b"
