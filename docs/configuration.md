# Configuration Reference

Recast uses two TOML configuration files:

- **`show.toml`** — per-show settings (one per show folder)
- **`recast_config.toml`** — global settings (in the working directory)

## show.toml — Full Reference

```toml
# ─── Show Metadata ───────────────────────────────────────────────
[show]
name = "My Podcast"                    # Show name (required)
description = "Description here"       # Show description
author = "Author Name"                 # Author/creator
language = "no"                        # Language code (ISO 639-1)
cover_image = "cover.jpg"              # Cover art (relative path, min 1400x1400 JPEG/PNG)

# ─── Input Settings ──────────────────────────────────────────────
[input]
watch_folder = "incoming"              # Folder to watch for new files (relative)
file_patterns = ["*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"]  # File patterns to match

# ─── Output Settings ─────────────────────────────────────────────
[output]
folder = "episodes"                    # Output folder for finished episodes (relative)
audio_format = "mp3"                   # Output format: mp3, wav
audio_bitrate = "192k"                 # Output bitrate (for mp3)

# ─── Pipeline Settings ───────────────────────────────────────────
[pipeline]
whisper_model = "NbAiLab/nb-whisper-small"  # ASR model (see table below)
language = "no"                        # Transcription language
ollama_model = "gemma3:12b"            # LLM model for content analysis
ollama_base_url = "http://localhost:11434"  # Ollama API endpoint
join_mode = "crossfade"                # How to join segments: crossfade | hard_cut | silence
crossfade_duration_ms = 300            # Crossfade duration (when join_mode = crossfade)
silence_duration_ms = 500              # Silence gap duration (when join_mode = silence)
cut_pad_ms = 300                       # Padding around cut boundaries
min_speech_gap_s = 0.5                 # Merge speech segments closer than this
min_keep_duration_s = 2.0              # Discard kept segments shorter than this
llm_confidence_threshold = 0.6         # Ignore LLM cuts below this confidence

# ─── Custom LLM Prompt ───────────────────────────────────────────
[pipeline.llm_prompt]
# template_file = "my_prompt.txt"      # Override the default LLM prompt template

# ─── Publishing Settings ─────────────────────────────────────────
[publishing]
auto_publish = true                    # Auto-publish after pipeline completes
review_mode = false                    # Pause at Stage 5 for human review

[publishing.rss]
enabled = true                         # Generate RSS feed
feed_file = "feed.xml"                 # Feed file name (relative to show folder)
feed_base_url = "https://your-domain.com/podcast"  # Base URL for episode MP3s

[publishing.apple_podcasts]
enabled = true                         # Include Apple Podcasts compliance tags

[publishing.rss.itunes]
category = "News"                      # iTunes category
subcategory = "Daily News"             # iTunes subcategory
explicit = false                       # Explicit content flag
```

### Whisper Models

| Model | ID | Size | Speed | Quality |
|-------|----|------|-------|---------|
| Small | `NbAiLab/nb-whisper-small` | ~500MB | Fast | Good (default) |
| Medium | `NbAiLab/nb-whisper-medium` | ~1.5GB | Medium | Better |
| Large | `NbAiLab/nb-whisper-large` | ~3GB | Slow | Best |

!!! tip
    Use `nb-whisper-small` during development and testing. Switch to `nb-whisper-large` for production quality.

### Join Modes

| Mode | Description |
|------|-------------|
| `crossfade` | Smooth audio transition between segments (default, 300ms) |
| `hard_cut` | Direct concatenation, no transition |
| `silence` | Insert a configurable silence gap between segments |

### Pipeline Tuning

| Setting | Default | Effect |
|---------|---------|--------|
| `cut_pad_ms` | 300 | More padding = smoother transitions but may clip speech |
| `min_speech_gap_s` | 0.5 | Lower = more fragmented segments; higher = more merged |
| `min_keep_duration_s` | 2.0 | Filters out tiny speech fragments |
| `llm_confidence_threshold` | 0.6 | Lower = more aggressive removal; higher = more conservative |

## recast_config.toml — Global Settings

Place in your working directory:

```toml
[recast]
shows_dir = "./shows"          # Root folder containing show subfolders
log_level = "info"             # debug / info / warning / error
log_file = "recast.log"        # Log file path

[ui]
host = "127.0.0.1"             # Web UI bind address
port = 8765                    # Web UI port
auto_open_browser = true       # Open browser on startup

[models]
hf_token = "hf_..."           # HuggingFace token (for pyannote model download)
```

## Custom LLM Prompt

The default prompt instructs the LLM to identify Norwegian radio content to remove. You can customize it per show:

1. Create a text file (e.g. `my_prompt.txt`) in your show folder
2. Reference it in `show.toml`:
    ```toml
    [pipeline.llm_prompt]
    template_file = "my_prompt.txt"
    ```

The prompt must contain `{transcript}` as a placeholder where the transcript text will be inserted.

**Default prompt:**
```
You are processing a Norwegian radio broadcast transcript.
Your task is to identify spoken segments that should be REMOVED to produce a clean podcast.

Remove:
- Song introductions (host announcing a song about to play)
- Song outros or dedications (host commenting on a song just played)
- Spoken station jingles or ID announcements
- Advertisement or sponsorship segments

Keep:
- All genuine conversation, interviews, debate, storytelling, news
- When in doubt, KEEP the segment

Return ONLY valid JSON. No explanation. Format:
[{"start": 12.4, "end": 18.9, "reason": "song introduction", "confidence": 0.9}, ...]

Transcript:
{transcript}
```
