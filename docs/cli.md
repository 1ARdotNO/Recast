# CLI Reference

## Commands

### `recast run`

Process a single file or all unprocessed files in a show's watch folder.

```bash
recast run <show-folder> [<input-file>]
```

**Examples:**
```bash
# Process a specific file
recast run myshow recording.mp3

# Process all unprocessed files in the watch folder
recast run myshow

# Dry run (no output written)
recast run myshow recording.mp3 --dry-run
```

### `recast watch`

Start watching one or more show folders for new audio files. Blocks until interrupted.

```bash
recast watch <show-folder> [<show-folder> ...]
```

**Examples:**
```bash
# Watch a single show
recast watch myshow

# Watch multiple shows
recast watch show1 show2 show3
```

### `recast status`

Print a table of recent jobs and their states.

```bash
recast status <show-folder>
```

**Output:**
```
ID       File                      Status     Stage        Error
------------------------------------------------------------------------------------------
a1b2c3d4 morgennytt_2025-03-22.mp3 done       publish
e5f6g7h8 morgennytt_2025-03-21.mp3 failed     llm_pass     Ollama connection timeout
```

### `recast retry`

Retry a failed job from the last successful stage.

```bash
recast retry <show-folder> <job-id>
```

You can use a prefix of the job ID:
```bash
recast retry myshow a1b2
```

### `recast publish`

Manually trigger publishing for an already-rendered episode.

```bash
recast publish <show-folder> <job-id>
```

### `recast ui`

Start the local web UI server.

```bash
recast ui [--host HOST] [--port PORT] [--no-open]
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8765` | Port number |
| `--no-open` | off | Don't auto-open browser |

### `recast update`

Check for updates and optionally install them.

```bash
recast update [--check] [--yes]
```

| Option | Description |
|--------|-------------|
| `--check` | Only check, don't install |
| `--yes, -y` | Skip confirmation prompt |

### `recast version`

Show the current version.

```bash
recast version
```

## Global Flags

Available on all commands:

| Flag | Default | Description |
|------|---------|-------------|
| `--config <path>` | `show.toml` in show folder | Override config file path |
| `--log-level` | `info` | `debug` / `info` / `warning` / `error` |
| `--no-color` | off | Disable ANSI color output |
| `--dry-run` | off | Run pipeline without writing output or publishing |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Pipeline error (logged) |
| 2 | Configuration error |
| 3 | Dependency missing (ffmpeg, Ollama) |
