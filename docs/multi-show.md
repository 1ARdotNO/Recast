# Multi-Show Setup

Recast supports managing multiple radio shows simultaneously. Each show is an independent folder with its own configuration, database, and output.

## Directory Structure

```
shows/
├── morgennytt/
│   ├── show.toml
│   ├── cover.jpg
│   ├── incoming/          # drop files here
│   ├── episodes/          # finished MP3s
│   ├── feed.xml           # RSS feed
│   └── .recast/
│       ├── recast.db      # job database
│       └── jobs/          # working files
├── kulturnytt/
│   ├── show.toml
│   ├── incoming/
│   ├── episodes/
│   └── .recast/
└── sportssending/
    ├── show.toml
    ├── incoming/
    ├── episodes/
    └── .recast/
```

## Global Config

Create `recast_config.toml` in your working directory pointing to the shows root:

```toml
[recast]
shows_dir = "./shows"
```

The web UI auto-discovers all subfolders containing `show.toml`.

## Per-Show Configuration

Each show can have different settings:

```toml
# shows/morgennytt/show.toml
[show]
name = "Morgennytt Deep Cuts"
language = "no"

[pipeline]
whisper_model = "NbAiLab/nb-whisper-large"   # high quality for flagship show
ollama_model = "gemma3:12b"
join_mode = "crossfade"
```

```toml
# shows/sportssending/show.toml
[show]
name = "Sportssending"
language = "no"

[pipeline]
whisper_model = "NbAiLab/nb-whisper-small"   # faster for sports updates
ollama_model = "llama3.2:3b"                 # lighter model
join_mode = "hard_cut"
```

## Single Show vs Multi-Show

### Single Show

For a single show, no `recast_config.toml` is needed. Just use the CLI directly:

```bash
recast run myshow recording.mp3
recast watch myshow
recast status myshow
```

### Multiple Shows

With multiple shows, `recast watch` can monitor all of them:

```bash
# Watch all shows at once
recast watch shows/morgennytt shows/kulturnytt shows/sportssending
```

The web UI dashboard shows all discovered shows:

```bash
recast ui
```

## Watching Multiple Shows

Each show runs its own pipeline worker independently. A slow job in one show doesn't block processing in another.

```bash
recast watch shows/*
```

## Publishing Multiple Shows

Each show has its own RSS feed. Configure different `feed_base_url` values for each:

```toml
# shows/morgennytt/show.toml
[publishing.rss]
feed_base_url = "https://cdn.example.com/morgennytt"

# shows/kulturnytt/show.toml
[publishing.rss]
feed_base_url = "https://cdn.example.com/kulturnytt"
```

Each show's `feed.xml` is independent and can be submitted to Spotify/Apple separately.

## Tips

- **Shared Ollama instance** — all shows use the same Ollama server by default (`localhost:11434`)
- **Different models per show** — some shows may need larger/smaller models depending on complexity
- **Review mode per show** — enable `review_mode = true` for new shows while calibrating, disable for established ones
- **Separate cover art** — each show should have its own `cover.jpg` for podcast directories
