"""Stage 4 — LLM Context Pass: Identify segments to remove using Ollama."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

logger = structlog.get_logger()

DEFAULT_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "llm_pass.txt"


def _load_prompt_template(custom_path: str | None = None) -> str:
    """Load the LLM prompt template."""
    if custom_path:
        path = Path(custom_path)
        if path.exists():
            return path.read_text()
    return DEFAULT_PROMPT_PATH.read_text()


def _format_transcript_for_prompt(transcript: dict) -> str:
    """Format transcript segments into text with timestamps."""
    lines = []
    for seg in transcript.get("segments", []):
        start = seg["start"]
        end = seg["end"]
        text = seg["text"]
        lines.append(f"[{start:.1f}s - {end:.1f}s] {text}")
    return "\n".join(lines)


def _parse_llm_response(response_text: str) -> list[dict]:
    """Parse the LLM JSON response, handling common formatting issues."""
    text = response_text.strip()

    # Try to extract JSON array from response
    start_idx = text.find("[")
    end_idx = text.rfind("]")

    if start_idx == -1 or end_idx == -1:
        # No JSON array found — model returned nothing to cut
        return []

    json_str = text[start_idx:end_idx + 1]

    try:
        result = json.loads(json_str)
        if not isinstance(result, list):
            return []
        return result
    except json.JSONDecodeError:
        logger.warning("llm_pass.parse_error", raw=json_str[:200])
        return []


def llm_pass(
    transcript: dict,
    output_dir: Path,
    ollama_model: str = "gemma3:12b",
    ollama_base_url: str = "http://localhost:11434",
    confidence_threshold: float = 0.6,
    prompt_template_path: str | None = None,
) -> list[dict]:
    """Run LLM context analysis on transcript to identify removable segments.

    Returns list of {start, end, reason, confidence} dicts.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "cuts_llm.json"

    logger.info("llm_pass.start", model=ollama_model)

    # Build prompt
    template = _load_prompt_template(prompt_template_path)
    transcript_text = _format_transcript_for_prompt(transcript)
    prompt = template.replace("{transcript}", transcript_text)

    # Call Ollama
    import ollama

    client = ollama.Client(host=ollama_base_url)

    response = client.chat(
        model=ollama_model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1},
    )

    response_text = response["message"]["content"]

    # Parse response
    cuts = _parse_llm_response(response_text)

    # Filter by confidence threshold
    filtered = []
    for cut in cuts:
        if not all(k in cut for k in ("start", "end")):
            continue
        confidence = cut.get("confidence", 0.5)
        if confidence >= confidence_threshold:
            filtered.append({
                "start": float(cut["start"]),
                "end": float(cut["end"]),
                "reason": cut.get("reason", "unknown"),
                "confidence": float(confidence),
            })

    # Save output
    output_path.write_text(json.dumps(filtered, indent=2))

    logger.info(
        "llm_pass.done",
        n_cuts_raw=len(cuts),
        n_cuts_filtered=len(filtered),
        threshold=confidence_threshold,
    )

    return filtered
