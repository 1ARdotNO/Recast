"""FastAPI app + WebSocket server for Recast web UI."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from recast.config import load_show_config, load_global_config, discover_shows
from recast.models.cut import CutList
from recast.models.job import JobStatus
from recast.queue import JobQueue

logger = structlog.get_logger()

app = FastAPI(title="Recast", version="0.1.0")

# Global state for WebSocket connections
_ws_connections: list[WebSocket] = []
_global_config: dict = {}


class ShowSummary(BaseModel):
    name: str
    folder: str
    n_jobs: int
    last_status: str | None


class JobSummary(BaseModel):
    id: str
    filename: str
    status: str
    stage: str | None
    created_at: str
    error: str | None


class CutListUpdate(BaseModel):
    decisions: list[dict]
    total_duration: float


class MetadataUpdate(BaseModel):
    title: str
    description: str
    chapters: list[dict]


class ShowSettingsUpdate(BaseModel):
    settings: dict


def _get_global_config() -> dict:
    global _global_config
    if not _global_config:
        _global_config = load_global_config()
    return _global_config


def _get_shows_dir() -> Path:
    cfg = _get_global_config()
    return Path(cfg.get("shows_dir", "./shows"))


# --- REST API ---

@app.get("/api/shows")
async def list_shows():
    shows_dir = _get_shows_dir()
    show_folders = discover_shows(shows_dir)
    results = []
    for folder in show_folders:
        try:
            config = load_show_config(folder)
            queue = JobQueue(config.db_path)
            jobs = queue.list_jobs(limit=1)
            results.append(ShowSummary(
                name=config.name,
                folder=str(folder),
                n_jobs=len(queue.list_jobs(limit=1000)),
                last_status=jobs[0].status.value if jobs else None,
            ))
        except Exception as e:
            logger.warning("api.show_error", folder=str(folder), error=str(e))
    return results


@app.get("/api/shows/{show_name}/jobs")
async def list_jobs(show_name: str, limit: int = 50, offset: int = 0):
    config = _find_show(show_name)
    queue = JobQueue(config.db_path)
    jobs = queue.list_jobs(limit=limit, offset=offset)
    return [
        JobSummary(
            id=j.id, filename=j.filename, status=j.status.value,
            stage=j.stage, created_at=j.created_at, error=j.error,
        )
        for j in jobs
    ]


@app.get("/api/shows/{show_name}/jobs/{job_id}")
async def get_job(show_name: str, job_id: str):
    config = _find_show(show_name)
    queue = JobQueue(config.db_path)
    job = queue.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    episode = queue.get_episode(job_id)
    return {
        "job": JobSummary(
            id=job.id, filename=job.filename, status=job.status.value,
            stage=job.stage, created_at=job.created_at, error=job.error,
        ),
        "episode": episode.to_dict() if episode else None,
    }


@app.get("/api/shows/{show_name}/jobs/{job_id}/cutlist")
async def get_cutlist(show_name: str, job_id: str):
    config = _find_show(show_name)
    job_dir = config.job_dir(job_id)

    # Prefer user cutlist
    user_path = job_dir / "cutlist_user.json"
    final_path = job_dir / "cutlist_final.json"

    if user_path.exists():
        return json.loads(user_path.read_text())
    elif final_path.exists():
        return json.loads(final_path.read_text())
    else:
        raise HTTPException(404, "Cut list not found")


@app.put("/api/shows/{show_name}/jobs/{job_id}/cutlist")
async def update_cutlist(show_name: str, job_id: str, update: CutListUpdate):
    config = _find_show(show_name)
    job_dir = config.job_dir(job_id)
    user_path = job_dir / "cutlist_user.json"

    cutlist = CutList.from_dict(update.model_dump())
    cutlist.save(user_path)
    return {"status": "saved"}


@app.get("/api/shows/{show_name}/jobs/{job_id}/transcript")
async def get_transcript(show_name: str, job_id: str):
    config = _find_show(show_name)
    path = config.job_dir(job_id) / "transcript.json"
    if not path.exists():
        raise HTTPException(404, "Transcript not found")
    return json.loads(path.read_text())


@app.get("/api/shows/{show_name}/jobs/{job_id}/audio")
async def get_audio(show_name: str, job_id: str, original: bool = False):
    config = _find_show(show_name)
    job_dir = config.job_dir(job_id)

    if original:
        path = job_dir / "audio_normalized.wav"
    else:
        path = job_dir / f"episode_audio.{config.audio_format}"

    if not path.exists():
        raise HTTPException(404, "Audio not found")

    media_type = "audio/wav" if path.suffix == ".wav" else "audio/mpeg"
    return FileResponse(path, media_type=media_type)


@app.post("/api/shows/{show_name}/jobs/{job_id}/render")
async def trigger_render(show_name: str, job_id: str):
    config = _find_show(show_name)
    queue = JobQueue(config.db_path)
    job = queue.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    # Run render in background
    import threading

    def _render():
        from recast.pipeline.stages.render import render
        from recast.models.cut import CutList

        job_dir = config.job_dir(job_id)
        wav = job_dir / "audio_normalized.wav"

        user_cutlist = job_dir / "cutlist_user.json"
        final_cutlist = job_dir / "cutlist_final.json"

        cl_path = user_cutlist if user_cutlist.exists() else final_cutlist
        cutlist = CutList.load(cl_path)

        render(
            wav, cutlist, job_dir,
            join_mode=config.join_mode,
            crossfade_duration_ms=config.crossfade_duration_ms,
            silence_duration_ms=config.silence_duration_ms,
            audio_format=config.audio_format,
            audio_bitrate=config.audio_bitrate,
        )

    threading.Thread(target=_render, daemon=True).start()
    return {"status": "rendering"}


@app.post("/api/shows/{show_name}/jobs/{job_id}/publish")
async def trigger_publish(show_name: str, job_id: str):
    config = _find_show(show_name)
    queue = JobQueue(config.db_path)
    job = queue.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    from recast.cli import _publish_episode
    _publish_episode(config, queue, job_id)

    # If job was in review, mark as done
    if job.status == JobStatus.REVIEW:
        job.complete()
        queue.update_job(job)

    return {"status": "published"}


@app.get("/api/shows/{show_name}/settings")
async def get_show_settings(show_name: str):
    config = _find_show(show_name)
    return {
        "name": config.name,
        "description": config.description,
        "author": config.author,
        "language": config.language,
        "cover_image": config.cover_image,
        "whisper_model": config.whisper_model,
        "ollama_model": config.ollama_model,
        "ollama_base_url": config.ollama_base_url,
        "join_mode": config.join_mode,
        "crossfade_duration_ms": config.crossfade_duration_ms,
        "silence_duration_ms": config.silence_duration_ms,
        "cut_pad_ms": config.cut_pad_ms,
        "min_speech_gap_s": config.min_speech_gap_s,
        "min_keep_duration_s": config.min_keep_duration_s,
        "llm_confidence_threshold": config.llm_confidence_threshold,
        "auto_publish": config.auto_publish,
        "review_mode": config.review_mode,
        "rss_enabled": config.rss_enabled,
        "feed_base_url": config.feed_base_url,
        "audio_format": config.audio_format,
        "audio_bitrate": config.audio_bitrate,
    }


@app.put("/api/shows/{show_name}/settings")
async def update_show_settings(show_name: str, update: ShowSettingsUpdate):
    config = _find_show(show_name)
    toml_path = config.show_folder / "show.toml"

    # Read existing TOML and update
    import tomllib
    if toml_path.exists():
        with open(toml_path, "rb") as f:
            existing = tomllib.load(f)
    else:
        existing = {}

    # Build updated TOML content
    settings = update.settings
    lines = ["[show]"]
    for key in ["name", "description", "author", "language", "cover_image"]:
        if key in settings:
            lines.append(f'{key} = "{settings[key]}"')
        elif key in existing.get("show", {}):
            lines.append(f'{key} = "{existing["show"][key]}"')

    lines.append("\n[pipeline]")
    pipe_keys = {
        "whisper_model": str, "ollama_model": str, "ollama_base_url": str,
        "join_mode": str, "language": str,
    }
    pipe_int_keys = {
        "crossfade_duration_ms": int, "silence_duration_ms": int,
        "cut_pad_ms": int,
    }
    pipe_float_keys = {
        "min_speech_gap_s": float, "min_keep_duration_s": float,
        "llm_confidence_threshold": float,
    }

    for key, _ in pipe_keys.items():
        if key in settings:
            lines.append(f'{key} = "{settings[key]}"')
    for key, _ in pipe_int_keys.items():
        if key in settings:
            lines.append(f'{key} = {int(settings[key])}')
    for key, _ in pipe_float_keys.items():
        if key in settings:
            lines.append(f'{key} = {float(settings[key])}')

    lines.append("\n[publishing]")
    if "auto_publish" in settings:
        lines.append(f'auto_publish = {"true" if settings["auto_publish"] else "false"}')
    if "review_mode" in settings:
        lines.append(f'review_mode = {"true" if settings["review_mode"] else "false"}')

    toml_path.write_text("\n".join(lines) + "\n")
    return {"status": "saved"}


@app.post("/api/shows/{show_name}/cover")
async def upload_cover(show_name: str, file: UploadFile = File(...)):
    config = _find_show(show_name)
    dest = config.show_folder / "cover.jpg"
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)
    return {"status": "uploaded", "path": str(dest)}


@app.get("/api/test/ollama")
async def test_ollama(base_url: str = "http://localhost:11434"):
    try:
        import ollama
        client = ollama.Client(host=base_url)
        models = client.list()
        return {
            "status": "ok",
            "models": [m.get("name", m.get("model", "")) for m in models.get("models", [])],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/test/ffmpeg")
async def test_ffmpeg():
    return {"available": shutil.which("ffmpeg") is not None}


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_connections.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _ws_connections.remove(ws)


async def broadcast_progress(stage: str, stage_idx: int, total: int, job_id: str = ""):
    """Broadcast pipeline progress to all WebSocket clients."""
    msg = json.dumps({
        "type": "progress",
        "job_id": job_id,
        "stage": stage,
        "stage_idx": stage_idx,
        "total": total,
    })
    for ws in _ws_connections.copy():
        try:
            await ws.send_text(msg)
        except Exception:
            _ws_connections.remove(ws)


# --- Static files ---

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


# --- Helpers ---

def _find_show(show_name: str):
    """Find a show by name."""
    shows_dir = _get_shows_dir()
    show_folders = discover_shows(shows_dir)

    for folder in show_folders:
        try:
            config = load_show_config(folder)
            if config.name == show_name or folder.name == show_name:
                return config
        except Exception:
            continue

    raise HTTPException(404, f"Show not found: {show_name}")
