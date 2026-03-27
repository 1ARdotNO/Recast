# Pipeline Stages

Recast processes audio through 8 sequential stages. Each stage writes output to disk, making the pipeline **resumable** — if interrupted, it restarts from the last completed stage.

## Stage 1 — Normalize

Converts the input audio to WAV 16kHz mono using ffmpeg.

- **Input:** Any audio format (MP3, WAV, M4A, OGG, FLAC)
- **Output:** `audio_normalized.wav`
- Original file is never modified

## Stage 2 — Segment

Detects speech vs non-speech (music/noise) regions.

- **Engine:** pyannote.audio (GPU) or energy-based VAD (fallback)
- **Output:** `segments_pyannote.json` — list of `{start, end, type}` objects
- Adjacent speech segments separated by less than `min_speech_gap_s` are merged
- This stage **classifies only** — nothing is removed yet

## Stage 3 — Transcribe

Speech-to-text with word-level timestamps.

- **Engine:** faster-whisper with NB-Whisper models
- **Output:** `transcript.json` — segments with word-level timestamps
- Only speech regions from Stage 2 are transcribed (music is skipped)
- Device auto-detection: CUDA → MPS → CPU

## Stage 4 — LLM Context Pass

The most critical stage. Uses a local LLM to identify spoken content that should be removed:

- Song introductions (host announcing upcoming tracks)
- Song outros/dedications
- Station jingles and IDs
- Advertisements

**How it works:**

1. Builds a prompt with the full timestamped transcript
2. Sends to Ollama (configurable model)
3. LLM returns JSON list of segments to remove with confidence scores
4. Segments below `llm_confidence_threshold` are ignored

- **Output:** `cuts_llm.json`
- The system prompt is configurable per show via `[pipeline.llm_prompt]`

## Stage 5 — Reconcile

Merges the pyannote cut list (Stage 2) and LLM cut list (Stage 4):

- **Union rule:** removed if flagged by EITHER source
- **Padding:** adds `cut_pad_ms` around cut boundaries
- **Minimum duration:** discards kept segments shorter than `min_keep_duration_s`
- **Output:** `cutlist_final.json` — the authoritative cut list

This is the data structure exposed in the Web UI Episode Editor. If the user edits cuts, their changes are saved as `cutlist_user.json` which takes precedence.

## Stage 6 — Render

Produces the final episode audio using ffmpeg:

- Extracts all `keep` segments
- Joins with the configured mode:
    - **crossfade** — smooth transitions (default, 300ms)
    - **hard_cut** — direct concatenation
    - **silence** — configurable gap between segments
- Encodes to the configured format (default: MP3 192kbps)
- **Output:** `episode_audio.mp3`

## Stage 7 — Metadata

Generates episode metadata using the LLM:

- **Episode title** — short, descriptive
- **Description** — 2-4 sentence summary
- **Chapter markers** — topic-based with timestamps

Chapters are written as ID3 CHAP/CTOC frames in the MP3 file.

- **Output:** `episode_metadata.json`

## Stage 8 — Publish

Updates the RSS feed with the new episode:

- Generates/updates `feed.xml` with RSS 2.0 + iTunes namespace tags
- Validates against Apple Podcasts and Spotify requirements
- Copies the final MP3 to the output folder

## Working Directory

Each job creates a scratch directory at `.recast/jobs/<job-id>/`:

```
<job-id>/
├── audio_normalized.wav       # Stage 1
├── segments_pyannote.json     # Stage 2
├── transcript.json            # Stage 3
├── cuts_llm.json              # Stage 4
├── cutlist_final.json         # Stage 5
├── cutlist_user.json          # Stage 5 (user edits, optional)
├── episode_audio.mp3          # Stage 6
└── episode_metadata.json      # Stage 7
```

## Resume Behavior

If the pipeline is interrupted (crash, Ctrl+C, power failure):

```bash
recast run myshow          # automatically resumes from last completed stage
recast retry myshow <id>   # retry a specific failed job
```

The runner checks for stage output files — if a stage's output exists, it's skipped.

## Retry Logic

Transient errors (Ollama timeout, ffmpeg crash) trigger up to **3 automatic retries** with exponential backoff (1s, 2s, 4s) before marking the job as failed.
