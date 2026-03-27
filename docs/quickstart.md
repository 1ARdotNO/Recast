# Quick Start

Get your first podcast episode from a radio recording in 5 minutes.

## 1. Create a Show Folder

```bash
mkdir -p myshow/incoming myshow/episodes
```

## 2. Create the Configuration

Create `myshow/show.toml`:

```toml
[show]
name = "My Podcast"
description = "Cleaned radio broadcasts"
author = "Your Name"
language = "no"

[pipeline]
whisper_model = "NbAiLab/nb-whisper-small"   # fast; use -large for accuracy
ollama_model = "gemma3:12b"

[publishing]
auto_publish = false
```

## 3. Process an Audio File

```bash
recast run myshow recording.mp3
```

This runs the full 8-stage pipeline:

```
  [1/8] normalize...
  [2/8] segment...
  [3/8] transcribe...
  [4/8] llm_pass...
  [5/8] reconcile...
  [6/8] render...
  [7/8] metadata...
  [8/8] publish...
  Done: Skattedebatten i Stortinget
```

The finished MP3 lands in `myshow/episodes/`.

## 4. Or Use the Web UI

```bash
recast ui
```

Opens http://localhost:8765 where you can:

- See all shows and their jobs on the **Dashboard**
- Review and edit cuts in the **Episode Editor**
- Configure settings via the **Show Settings** form

## 5. Auto-Watch for New Files

```bash
recast watch myshow
```

Drop audio files into `myshow/incoming/` and they're processed automatically.

## What's Next?

- [Web UI Guide](gui.md) — learn the browser interface in detail
- [CLI Reference](cli.md) — all available commands
- [Configuration](configuration.md) — tune the pipeline for your shows
- [Multi-Show Setup](multi-show.md) — manage multiple radio shows
