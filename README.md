# Recast

Radio broadcast to podcast converter with local AI, multi-show support, and automated publishing.

## Download & Install

Pre-built binaries are available for all platforms — no Python required:

| Platform | Download |
|----------|----------|
| **Windows** | [recast-windows-x86_64.exe](https://github.com/1ARdotNO/Recast/releases/latest/download/recast-windows-x86_64.exe) |
| **macOS (Apple Silicon)** | [recast-macos-arm64](https://github.com/1ARdotNO/Recast/releases/latest/download/recast-macos-arm64) |
| **Linux** | [recast-linux-x86_64](https://github.com/1ARdotNO/Recast/releases/latest/download/recast-linux-x86_64) |

Or see [all releases](https://github.com/1ARdotNO/Recast/releases).

### Windows Setup

1. Download `recast-windows-x86_64.exe` from the link above
2. Place it somewhere on your PATH (e.g. `C:\Program Files\Recast\`)
3. Install ffmpeg:
   ```powershell
   # Try winget first (built into Windows 11 / Windows 10 1709+):
   winget install --id Gyan.FFmpeg --accept-source-agreements

   # If winget is not available, use Chocolatey:
   choco install ffmpeg -y
   ```
4. Install [Ollama](https://ollama.ai) and pull a model:
   ```powershell
   ollama pull gemma3:12b
   ```
5. Run Recast:
   ```powershell
   recast-windows-x86_64.exe ui
   ```

### macOS Setup

1. Download `recast-macos-arm64` and make it executable:
   ```bash
   chmod +x recast-macos-arm64
   sudo mv recast-macos-arm64 /usr/local/bin/recast
   ```
2. Install dependencies:
   ```bash
   brew install ffmpeg
   ```
3. Install [Ollama](https://ollama.ai) and pull a model:
   ```bash
   ollama pull gemma3:12b
   ```
4. Run: `recast ui`

### Linux Setup

1. Download `recast-linux-x86_64` and make it executable:
   ```bash
   chmod +x recast-linux-x86_64
   sudo mv recast-linux-x86_64 /usr/local/bin/recast
   ```
2. Install dependencies:
   ```bash
   sudo apt update && sudo apt install ffmpeg    # Debian/Ubuntu
   # or: sudo dnf install ffmpeg                 # Fedora
   ```
3. Install [Ollama](https://ollama.ai) and pull a model:
   ```bash
   ollama pull gemma3:12b
   ```
4. Run: `recast ui`

## Features

- Watches input folders for new audio files and auto-processes them
- Local AI pipeline: music detection, transcription, spoken-intro removal, audio stitching
- Generates episode titles, descriptions, and chapter markers via LLM
- Publishes to Spotify and Apple Podcasts via RSS feed
- Web UI for reviewing cuts, editing segments, and managing shows
- CLI mode for headless, scriptable operation
- All inference runs locally — no data leaves your machine

## Web UI Guide

Start the web UI with `recast ui` and open http://localhost:8765 in your browser.

### Dashboard

The dashboard shows all configured shows with job counts and quick actions.

![Dashboard](docs/screenshots/dashboard.png)

- Click **Jobs** to see the processing queue for a show
- Click **Settings** to configure the show parameters
- Shows are auto-discovered from the `shows_dir` in `recast_config.toml`

### Job List

The job list shows all processing jobs for a show with status badges, current pipeline stage, and error details.

![Job List](docs/screenshots/jobs.png)

- Status badges: `queued` / `running` / `review needed` / `done` / `failed`
- Click any row to open the Episode Editor

### Episode Editor

The core review interface. Click on a job to open the editor with waveform, cut list, transcript, and metadata panels.

![Episode Editor — Waveform and Cut List](docs/screenshots/editor.png)

- **Waveform panel** — Color-coded audio visualization
  - Green: kept (speech)
  - Red: removed (music, detected by pyannote)
  - Orange: removed (spoken intro/outro, detected by LLM)
  - Grey: removed (below minimum duration threshold)
  - Hover any region to see start/end times, duration, reason, and confidence
  - Click anywhere to seek

- **Cut list panel** — Table of all cut decisions with Restore/Remove buttons

- **Transcript panel** — Full transcript with timestamps, removed segments shown as strikethrough

Scroll down for metadata editing and bulk actions:

![Episode Editor — Metadata and Actions](docs/screenshots/editor_panels.png)

- **Metadata panel** — Edit episode title, description, and chapter markers
- **Bulk actions**: "Restore All LLM Cuts" and "Restore All Pyannote Cuts"
- **Actions**: Save edits, Render & Preview, Approve & Publish, Discard

### Show Settings

Edit all `show.toml` parameters via a form — no manual TOML editing required.

![Show Settings](docs/screenshots/settings.png)

- Configure Whisper model, Ollama model, join mode, padding, thresholds
- Test Ollama connection (pings endpoint, lists available models)
- Test ffmpeg availability

### Live Processing Log

Real-time pipeline progress with stage counter (Stage N of 8) and estimated time remaining.

![Live Processing Log](docs/screenshots/livelog.png)

- WebSocket-connected real-time updates
- Progress bar showing current stage
- Scrollable log of processing events

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

## Install from Source

For development or if you prefer pip:

```bash
git clone https://github.com/1ARdotNO/Recast.git
cd Recast
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
pip install -e ".[dev]"
```

## Development

```bash
pip install -e ".[dev]"
pytest                       # Run tests
pytest --cov=recast          # Run with coverage
pytest tests/test_runner.py -v  # Run specific tests
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
