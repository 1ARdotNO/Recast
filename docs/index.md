# Recast

**Radio broadcast to podcast converter with local AI, multi-show support, and automated publishing.**

Recast watches your input folders for new audio files and automatically processes them through a local AI pipeline that removes music, jingles, and ads — producing clean podcast episodes with generated titles, descriptions, and chapter markers.

## Key Features

- **Fully local AI** — no data leaves your machine
- **8-stage pipeline** — normalize, segment, transcribe, LLM analysis, reconcile, render, metadata, publish
- **Web UI** — review cuts, edit segments, manage shows in your browser
- **CLI mode** — fully headless, scriptable, CI/CD-friendly
- **Multi-show support** — watch multiple radio shows simultaneously
- **Auto-publish** — RSS feeds for Spotify and Apple Podcasts
- **Resumable** — if interrupted, restarts from the last completed stage
- **Cross-platform** — Windows, macOS, Linux

## Quick Links

- [Installation](installation.md) — download and set up Recast
- [Quick Start](quickstart.md) — process your first audio file in 5 minutes
- [Web UI Guide](gui.md) — learn the browser interface
- [CLI Reference](cli.md) — all commands and flags
- [Configuration](configuration.md) — `show.toml` and `recast_config.toml` reference
- [Multi-Show Setup](multi-show.md) — manage multiple radio shows

## How It Works

```
Audio File → Normalize → Segment → Transcribe → LLM Analysis → Reconcile → Render → Metadata → Publish
                (ffmpeg)   (pyannote)  (NB-Whisper)   (Ollama)     (merge)    (ffmpeg)  (Ollama)    (RSS)
```

1. **Normalize** — converts to WAV 16kHz mono
2. **Segment** — detects speech vs music regions
3. **Transcribe** — speech-to-text with word-level timestamps
4. **LLM Pass** — identifies spoken song intros, ads, jingles to remove
5. **Reconcile** — merges detection results into a final cut list
6. **Render** — stitches kept segments with crossfade/silence/hard-cut
7. **Metadata** — generates episode title, description, and chapters
8. **Publish** — updates RSS feed for Spotify/Apple Podcasts

## Screenshots

### Dashboard
![Dashboard](screenshots/dashboard.png)

### Episode Editor
![Editor](screenshots/editor.png)
