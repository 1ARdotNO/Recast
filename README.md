# Recast

Radio broadcast to podcast converter with local AI, multi-show support, and automated publishing.

## Features

- Watches input folders for new audio files and auto-processes them
- Local AI pipeline: music detection, transcription, spoken-intro removal, audio stitching
- Generates episode titles, descriptions, and chapter markers via LLM
- Publishes to Spotify and Apple Podcasts via RSS feed
- Web UI for reviewing cuts, editing segments, and managing shows
- CLI mode for headless, scriptable operation
- All inference runs locally — no data leaves your machine

## Prerequisites

| Tool | Required | Install |
|------|----------|---------|
| Python 3.11+ | Yes | [python.org](https://python.org) |
| ffmpeg | Yes | See below |
| Ollama | Yes | [ollama.ai](https://ollama.ai) |

### Install ffmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows:**
```powershell
winget install ffmpeg
# or download from https://ffmpeg.org/download.html and add to PATH
```

### Install Ollama

Download from [ollama.ai](https://ollama.ai), then pull a model:

```bash
ollama pull gemma3:12b
# or for faster CPU inference:
ollama pull llama3.2:3b
```

## Installation

### From source (recommended for development)

```bash
git clone https://github.com/your-org/recast.git
cd recast
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
pip install -e ".[dev]"
```

### Via pipx (user install)

```bash
pipx install .
```

### Optional: GPU support (pyannote.audio)

For GPU-accelerated speech segmentation:

```bash
pip install -e ".[gpu]"
```

## Quick Start

### 1. Create a show folder

```bash
mkdir -p myshow/incoming myshow/episodes
```

### 2. Create `myshow/show.toml`

```toml
[show]
name = "My Podcast"
description = "Cleaned radio broadcasts"
author = "Your Name"
language = "no"

[pipeline]
whisper_model = "NbAiLab/nb-whisper-small"  # small for speed, large for accuracy
ollama_model = "gemma3:12b"

[publishing]
auto_publish = false
```

### 3. Process an audio file

```bash
recast run myshow recording.mp3
```

### 4. Or watch for new files

```bash
recast watch myshow
```

### 5. Start the web UI

```bash
recast ui
```

Opens at http://localhost:8765 with dashboard, episode editor, and live processing log.

## CLI Reference

```
recast run <show-folder> [<input-file>]   Process file(s) through the pipeline
recast watch <show-folder> [...]          Watch folders for new audio files
recast status <show-folder>               Show recent job statuses
recast retry <show-folder> <job-id>       Retry a failed job
recast publish <show-folder> <job-id>     Manually publish an episode
recast ui [--host HOST] [--port PORT]     Start the web UI
```

### Global flags

| Flag | Default | Description |
|------|---------|-------------|
| `--config <path>` | `show.toml` | Override config path |
| `--log-level` | `info` | `debug / info / warning / error` |
| `--no-color` | off | Disable ANSI color output |
| `--dry-run` | off | Run pipeline without writing output |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Pipeline error |
| 2 | Configuration error |
| 3 | Dependency missing |

## Pipeline Stages

1. **Normalize** — Convert to WAV 16kHz mono (ffmpeg)
2. **Segment** — Detect speech vs music regions (pyannote / energy VAD)
3. **Transcribe** — ASR with NB-Whisper (word-level timestamps)
4. **LLM Pass** — Identify spoken intros, jingles, ads to remove (Ollama)
5. **Reconcile** — Merge detection results into final cut list
6. **Render** — Stitch kept segments with crossfade/silence/hard-cut (ffmpeg)
7. **Metadata** — Generate title, description, chapters (Ollama)
8. **Publish** — Update RSS feed for Spotify/Apple Podcasts

The pipeline is resumable — if interrupted, it restarts from the last completed stage.

## Configuration

### Whisper models

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `NbAiLab/nb-whisper-small` | ~500MB | Fast | Good (default) |
| `NbAiLab/nb-whisper-medium` | ~1.5GB | Medium | Better |
| `NbAiLab/nb-whisper-large` | ~3GB | Slow | Best |

Set in `show.toml` under `[pipeline] whisper_model`.

### Join modes

- `crossfade` — Smooth transitions between segments (default, 300ms)
- `hard_cut` — Direct concatenation
- `silence` — Insert configurable silence gap between segments

## Publishing

Recast generates standard RSS 2.0 feeds with iTunes namespace tags. Both Spotify and Apple Podcasts read these feeds.

**First-time setup (one-time per platform):**

1. Set `feed_base_url` in `show.toml` to where your MP3s are hosted
2. Submit your feed URL at [podcasters.spotify.com](https://podcasters.spotify.com)
3. Submit your feed URL at [podcastsconnect.apple.com](https://podcastsconnect.apple.com)

After that, new episodes appear automatically when the feed is updated.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=recast

# Run a specific test
pytest tests/test_runner.py -v
```

## Platform Support

| Platform | Status |
|----------|--------|
| macOS (Apple Silicon + Intel) | Supported |
| Linux (x86_64) | Supported |
| Windows (x86_64) | Supported |

GPU acceleration is auto-detected: CUDA (NVIDIA) and MPS (Apple Silicon) are used when available. CPU-only is fully supported.

## License

MIT
