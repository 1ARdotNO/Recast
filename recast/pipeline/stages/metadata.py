"""Stage 7 — Metadata: Generate title, description, and chapters via Ollama."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from recast.models.episode import Episode, Chapter

logger = structlog.get_logger()

METADATA_PROMPT = """\
You are analyzing a podcast episode transcript to generate metadata.

Generate the following in JSON format:
1. "title": A short, descriptive episode title based on the main topics discussed (max 100 chars)
2. "description": A 2-4 sentence summary suitable for podcast directories
3. "chapters": A list of chapter markers based on topic changes, each with "title" and "start_time" (in seconds)

Return ONLY valid JSON. No explanation. Format:
{{"title": "...", "description": "...", "chapters": [{{"title": "...", "start_time": 0.0}}, ...]}}

Transcript:
{transcript}
"""


def _format_transcript(transcript: dict) -> str:
    """Format transcript for the metadata prompt."""
    lines = []
    for seg in transcript.get("segments", []):
        lines.append(f"[{seg['start']:.1f}s] {seg['text']}")
    return "\n".join(lines)


def _parse_metadata_response(response_text: str) -> dict:
    """Parse the LLM metadata response."""
    text = response_text.strip()

    # Try to find JSON object
    start_idx = text.find("{")
    end_idx = text.rfind("}")

    if start_idx == -1 or end_idx == -1:
        return {"title": "", "description": "", "chapters": []}

    try:
        data = json.loads(text[start_idx:end_idx + 1])
        return {
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "chapters": data.get("chapters", []),
        }
    except json.JSONDecodeError:
        logger.warning("metadata.parse_error", raw=text[:200])
        return {"title": "", "description": "", "chapters": []}


def _write_id3_chapters(mp3_path: Path, chapters: list[Chapter], duration_s: float) -> None:
    """Write chapter metadata to MP3 ID3 tags using mutagen."""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import CTOC, CHAP, TIT2

        audio = MP3(str(mp3_path))
        if audio.tags is None:
            audio.add_tags()

        # Add CHAP frames
        chapter_ids = []
        for i, ch in enumerate(chapters):
            chap_id = f"chp{i}"
            chapter_ids.append(chap_id)

            start_ms = int(ch.start_time * 1000)
            end_ms = int(
                chapters[i + 1].start_time * 1000
                if i + 1 < len(chapters)
                else duration_s * 1000
            )

            audio.tags.add(CHAP(
                element_id=chap_id,
                start_time=start_ms,
                end_time=end_ms,
                sub_frames=[TIT2(encoding=3, text=[ch.title])],
            ))

        # Add CTOC (table of contents)
        if chapter_ids:
            audio.tags.add(CTOC(
                element_id="toc",
                flags=3,  # ordered + top-level
                child_element_ids=chapter_ids,
            ))

        audio.save()
        logger.info("metadata.id3_written", n_chapters=len(chapters))

    except Exception as e:
        logger.warning("metadata.id3_error", error=str(e))


def metadata(
    transcript: dict,
    output_dir: Path,
    episode_audio_path: Path | None = None,
    duration_s: float = 0.0,
    job_id: str = "",
    ollama_model: str = "gemma3:12b",
    ollama_base_url: str = "http://localhost:11434",
) -> Episode:
    """Generate episode metadata using Ollama.

    Returns an Episode object with title, description, and chapters.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "episode_metadata.json"

    logger.info("metadata.start", model=ollama_model)

    transcript_text = _format_transcript(transcript)
    prompt = METADATA_PROMPT.replace("{transcript}", transcript_text)

    import ollama as ollama_lib
    client = ollama_lib.Client(host=ollama_base_url)

    response = client.chat(
        model=ollama_model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.3},
    )

    response_text = response["message"]["content"]
    parsed = _parse_metadata_response(response_text)

    chapters = [
        Chapter(title=c["title"], start_time=float(c["start_time"]))
        for c in parsed.get("chapters", [])
    ]

    episode = Episode(
        job_id=job_id,
        output_path=str(episode_audio_path or ""),
        title=parsed.get("title", ""),
        description=parsed.get("description", ""),
        duration_s=duration_s,
        chapters=chapters,
    )

    episode.save(output_path)

    # Write ID3 chapters if MP3 exists
    if episode_audio_path and episode_audio_path.exists():
        if episode_audio_path.suffix.lower() == ".mp3":
            _write_id3_chapters(episode_audio_path, chapters, duration_s)

    logger.info(
        "metadata.done",
        title=episode.title,
        n_chapters=len(chapters),
    )

    return episode
