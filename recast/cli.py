"""Typer CLI entrypoint for Recast."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import structlog
import typer

from recast.logging import setup_logging

app = typer.Typer(
    name="recast",
    help="Radio broadcast to podcast converter with local AI.",
    no_args_is_help=True,
)

logger = structlog.get_logger()


def _check_ffmpeg() -> bool:
    """Check if ffmpeg is on PATH."""
    return shutil.which("ffmpeg") is not None


def _check_ollama(base_url: str = "http://localhost:11434") -> bool:
    """Check if Ollama is reachable."""
    try:
        import ollama
        client = ollama.Client(host=base_url)
        client.list()
        return True
    except Exception:
        return False


def _check_ollama_model(model: str, base_url: str = "http://localhost:11434") -> bool:
    """Check if a specific Ollama model is available."""
    try:
        import ollama
        client = ollama.Client(host=base_url)
        models = client.list()
        model_names = [m.get("name", m.get("model", "")) for m in models.get("models", [])]
        return any(model in name for name in model_names)
    except Exception:
        return False


def _check_dependencies(ollama_url: str = "http://localhost:11434", model: str = "gemma3:12b"):
    """Check all required dependencies and print actionable messages."""
    errors = []

    if not _check_ffmpeg():
        errors.append(
            "ffmpeg not found on PATH.\n"
            "  Install: https://ffmpeg.org/download.html\n"
            "  macOS: brew install ffmpeg\n"
            "  Ubuntu: sudo apt install ffmpeg"
        )

    if not _check_ollama(ollama_url):
        errors.append(
            f"Ollama not reachable at {ollama_url}.\n"
            "  Install: https://ollama.ai\n"
            "  Start: ollama serve"
        )
    elif not _check_ollama_model(model, ollama_url):
        errors.append(
            f"Ollama model '{model}' not found.\n"
            f"  Pull it: ollama pull {model}"
        )

    return errors


@app.command()
def run(
    show_folder: Path = typer.Argument(..., help="Path to show folder"),
    input_file: Optional[Path] = typer.Argument(None, help="Specific file to process"),
    config: Optional[Path] = typer.Option(None, "--config", help="Override config path"),
    log_level: str = typer.Option("info", "--log-level"),
    no_color: bool = typer.Option(False, "--no-color"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Process a single file or all unprocessed files."""
    setup_logging(log_level, no_color=no_color)

    from recast.config import load_show_config, load_global_config
    from recast.queue import JobQueue
    from recast.pipeline.runner import PipelineRunner

    try:
        show_config = load_show_config(show_folder, config)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Configuration error: {e}", err=True)
        raise typer.Exit(2)

    global_config = load_global_config()

    # Dependency checks
    dep_errors = _check_dependencies(
        show_config.ollama_base_url, show_config.ollama_model,
    )
    for err in dep_errors:
        typer.echo(f"WARNING: {err}", err=True)

    if not _check_ffmpeg():
        raise typer.Exit(3)

    queue = JobQueue(show_config.db_path)
    runner = PipelineRunner(
        show_config, queue,
        hf_token=global_config.get("hf_token", ""),
        dry_run=dry_run,
        progress_callback=lambda stage, idx, total: typer.echo(
            f"  [{idx}/{total}] {stage}..."
        ),
    )

    if input_file:
        files = [input_file]
    else:
        # Process all unprocessed files
        watch_path = show_config.watch_path
        if not watch_path.exists():
            typer.echo(f"Watch folder not found: {watch_path}", err=True)
            raise typer.Exit(2)

        import fnmatch
        files = [
            f for f in watch_path.iterdir()
            if f.is_file() and any(
                fnmatch.fnmatch(f.name, p) for p in show_config.file_patterns
            )
        ]

    if not files:
        typer.echo("No files to process.")
        raise typer.Exit(0)

    for file_path in files:
        typer.echo(f"Processing: {file_path.name}")
        job = queue.create_job(file_path.name, str(file_path))
        episode = runner.run(job)

        if episode:
            typer.echo(f"  Done: {episode.title}")
            # Auto-publish if configured
            if show_config.auto_publish and not dry_run:
                _publish_episode(show_config, queue, job.id)
        else:
            db_job = queue.get_job(job.id)
            if db_job and db_job.status.value == "failed":
                typer.echo(f"  Failed: {db_job.error}", err=True)
                raise typer.Exit(1)
            elif db_job and db_job.status.value == "review":
                typer.echo("  Paused for review. Use the web UI to approve.")


@app.command()
def watch(
    show_folders: list[Path] = typer.Argument(..., help="Show folder(s) to watch"),
    config: Optional[Path] = typer.Option(None, "--config"),
    log_level: str = typer.Option("info", "--log-level"),
    no_color: bool = typer.Option(False, "--no-color"),
):
    """Start watching show folders for new audio files."""
    setup_logging(log_level, no_color=no_color)

    from recast.config import load_show_config, load_global_config
    from recast.queue import JobQueue
    from recast.pipeline.runner import PipelineRunner
    from recast.watcher import ShowWatcher

    global_config = load_global_config()
    watcher = ShowWatcher()

    for folder in show_folders:
        try:
            show_config = load_show_config(folder, config)
        except (FileNotFoundError, ValueError) as e:
            typer.echo(f"Skipping {folder}: {e}", err=True)
            continue

        def process_file(path: Path, cfg=show_config):
            q = JobQueue(cfg.db_path)
            r = PipelineRunner(cfg, q, hf_token=global_config.get("hf_token", ""))
            job = q.create_job(path.name, str(path))
            episode = r.run(job)
            if episode and cfg.auto_publish:
                _publish_episode(cfg, q, job.id)

        watcher.add_show(show_config, process_file)
        typer.echo(f"Watching: {show_config.name} ({show_config.watch_path})")

    if not watcher._handlers:
        typer.echo("No valid shows to watch.", err=True)
        raise typer.Exit(2)

    watcher.start()
    typer.echo("Watching for new files. Press Ctrl+C to stop.")
    watcher.wait()


@app.command()
def status(
    show_folder: Path = typer.Argument(..., help="Show folder"),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """Show recent job statuses."""
    from recast.config import load_show_config
    from recast.queue import JobQueue

    try:
        show_config = load_show_config(show_folder, config)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(2)

    queue = JobQueue(show_config.db_path)
    jobs = queue.list_jobs(limit=20)

    if not jobs:
        typer.echo("No jobs found.")
        return

    typer.echo(f"{'ID':8} {'File':25} {'Status':10} {'Stage':12} {'Error':30}")
    typer.echo("-" * 90)
    for job in jobs:
        error = (job.error or "")[:30]
        typer.echo(
            f"{job.id[:8]:8} {job.filename:25} {job.status.value:10} "
            f"{(job.stage or '-'):12} {error:30}"
        )


@app.command()
def retry(
    show_folder: Path = typer.Argument(..., help="Show folder"),
    job_id: str = typer.Argument(..., help="Job ID to retry"),
    config: Optional[Path] = typer.Option(None, "--config"),
    log_level: str = typer.Option("info", "--log-level"),
):
    """Retry a failed job from last successful stage."""
    setup_logging(log_level)

    from recast.config import load_show_config, load_global_config
    from recast.queue import JobQueue
    from recast.pipeline.runner import PipelineRunner

    try:
        show_config = load_show_config(show_folder, config)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(2)

    global_config = load_global_config()
    queue = JobQueue(show_config.db_path)

    # Find job by prefix match
    jobs = queue.list_jobs(limit=1000)
    job = None
    for j in jobs:
        if j.id.startswith(job_id):
            job = j
            break

    if not job:
        typer.echo(f"Job not found: {job_id}", err=True)
        raise typer.Exit(1)

    # Reset to running
    job.error = None
    job.status = __import__("recast.models.job", fromlist=["JobStatus"]).JobStatus.QUEUED
    queue.update_job(job)

    runner = PipelineRunner(
        show_config, queue,
        hf_token=global_config.get("hf_token", ""),
        progress_callback=lambda stage, idx, total: typer.echo(
            f"  [{idx}/{total}] {stage}..."
        ),
    )

    typer.echo(f"Retrying job {job.id[:8]} ({job.filename})...")
    episode = runner.run(job)
    if episode:
        typer.echo(f"  Done: {episode.title}")
    else:
        typer.echo("  Failed or paused for review.", err=True)


@app.command()
def publish(
    show_folder: Path = typer.Argument(..., help="Show folder"),
    job_id: str = typer.Argument(..., help="Job ID to publish"),
    config: Optional[Path] = typer.Option(None, "--config"),
):
    """Manually publish an already-rendered episode."""
    from recast.config import load_show_config
    from recast.queue import JobQueue

    try:
        show_config = load_show_config(show_folder, config)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(2)

    queue = JobQueue(show_config.db_path)
    _publish_episode(show_config, queue, job_id)
    typer.echo("Published.")


@app.command()
def ui(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    no_open: bool = typer.Option(False, "--no-open"),
    log_level: str = typer.Option("info", "--log-level"),
):
    """Start the local web UI server."""
    setup_logging(log_level)

    typer.echo(f"Starting Recast UI at http://{host}:{port}")

    if not no_open:
        import webbrowser
        import threading
        threading.Timer(1.0, webbrowser.open, args=[f"http://{host}:{port}"]).start()

    try:
        from recast.server import app as server_app
    except Exception as e:
        typer.echo(f"Failed to load server: {e}", err=True)
        raise typer.Exit(1)

    import uvicorn

    config = uvicorn.Config(
        server_app,
        host=host,
        port=port,
        log_level=log_level,
    )
    server = uvicorn.Server(config)
    server.run()


@app.command()
def update(
    check_only: bool = typer.Option(False, "--check", help="Only check, don't install"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Check for updates and optionally install them."""
    from recast import __version__
    from recast.updater import check_for_update, perform_update, restart_app

    typer.echo(f"Current version: v{__version__}")
    typer.echo("Checking for updates...")

    update_info = check_for_update(__version__)

    if not update_info:
        typer.echo("You are on the latest version.")
        return

    typer.echo(f"New version available: {update_info['latest_version']}")
    typer.echo(f"Release: {update_info['release_url']}")

    if check_only:
        return

    if not yes:
        proceed = typer.confirm("Download and install update?")
        if not proceed:
            typer.echo("Update cancelled.")
            return

    typer.echo("Downloading update...")
    success = perform_update(update_info)

    if success:
        typer.echo(f"Updated to {update_info['latest_version']}!")
        if typer.confirm("Restart now?", default=True):
            restart_app()
    else:
        typer.echo("Update failed. See logs for details.", err=True)
        raise typer.Exit(1)


@app.command()
def version():
    """Show current version."""
    from recast import __version__
    typer.echo(f"recast v{__version__}")


def _check_update_notification() -> None:
    """Non-blocking update check on startup (silent)."""
    try:
        from recast import __version__
        from recast.updater import check_for_update
        update_info = check_for_update(__version__)
        if update_info:
            typer.echo(
                f"\nUpdate available: {update_info['latest_version']} "
                f"(current: v{__version__}). Run 'recast update' to install.\n",
                err=True,
            )
    except Exception:
        pass


def _publish_episode(show_config, queue, job_id: str) -> None:
    """Publish an episode (generate/update RSS feed)."""
    from recast.publishing.rss import generate_feed
    from recast.publishing.apple import validate_apple_compliance
    from datetime import datetime, timezone

    episode = queue.get_episode(job_id)
    if not episode:
        typer.echo(f"Episode not found for job {job_id}", err=True)
        return

    episode.published_at = datetime.now(timezone.utc).isoformat()
    episode.feed_updated = True
    queue.update_episode(episode)

    # Collect all published episodes
    all_jobs = queue.list_jobs(limit=1000)
    all_episodes = []
    for j in all_jobs:
        ep = queue.get_episode(j.id)
        if ep and ep.feed_updated:
            all_episodes.append(ep)

    # Generate feed
    _, warnings = generate_feed(show_config, all_episodes)

    # Check Apple compliance
    apple_issues = validate_apple_compliance(show_config)

    for w in warnings:
        typer.echo(f"  Warning: {w}", err=True)
    for issue in apple_issues:
        typer.echo(f"  Apple Podcasts: {issue}", err=True)
