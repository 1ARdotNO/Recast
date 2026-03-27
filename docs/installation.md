# Installation

## Download Pre-built Binaries

The easiest way to install Recast. No Python required.

| Platform | Download |
|----------|----------|
| **Windows** | [recast-windows-x86_64.exe](https://github.com/1ARdotNO/Recast/releases/latest/download/recast-windows-x86_64.exe) |
| **macOS (Apple Silicon)** | [recast-macos-arm64](https://github.com/1ARdotNO/Recast/releases/latest/download/recast-macos-arm64) |
| **Linux** | [recast-linux-x86_64](https://github.com/1ARdotNO/Recast/releases/latest/download/recast-linux-x86_64) |

All releases: [github.com/1ARdotNO/Recast/releases](https://github.com/1ARdotNO/Recast/releases)

## Platform-Specific Setup

=== "Windows"

    1. Download `recast-windows-x86_64.exe` from the link above
    2. Place it somewhere on your PATH (e.g. `C:\Program Files\Recast\`)
    3. Install ffmpeg:
        ```powershell
        # Try winget first (Windows 11 / Windows 10 1709+):
        winget install --id Gyan.FFmpeg --accept-source-agreements

        # If winget is not available, use Chocolatey:
        choco install ffmpeg -y
        ```
    4. Install [Ollama](https://ollama.ai) and pull a model:
        ```powershell
        ollama pull gemma3:12b
        ```
    5. Run:
        ```powershell
        recast-windows-x86_64.exe ui
        ```

=== "macOS"

    1. Download and install:
        ```bash
        chmod +x recast-macos-arm64
        sudo mv recast-macos-arm64 /usr/local/bin/recast
        ```
    2. Install ffmpeg:
        ```bash
        brew install ffmpeg
        ```
    3. Install [Ollama](https://ollama.ai) and pull a model:
        ```bash
        ollama pull gemma3:12b
        ```
    4. Run: `recast ui`

=== "Linux"

    1. Download and install:
        ```bash
        chmod +x recast-linux-x86_64
        sudo mv recast-linux-x86_64 /usr/local/bin/recast
        ```
    2. Install ffmpeg:
        ```bash
        sudo apt update && sudo apt install ffmpeg    # Debian/Ubuntu
        sudo dnf install ffmpeg                       # Fedora
        sudo pacman -S ffmpeg                         # Arch
        ```
    3. Install [Ollama](https://ollama.ai) and pull a model:
        ```bash
        curl -fsSL https://ollama.ai/install.sh | sh
        ollama pull gemma3:12b
        ```
    4. Run: `recast ui`

## Install from Source

For development or if you prefer pip:

```bash
git clone https://github.com/1ARdotNO/Recast.git
cd Recast
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pip install -e ".[dev]"
```

## Prerequisites

| Tool | Required | Purpose |
|------|----------|---------|
| **ffmpeg** | Yes | Audio conversion and rendering |
| **Ollama** | Yes | Local LLM for content analysis and metadata |
| Python 3.11+ | Only for source install | Runtime |

### Ollama Models

| Model | Size | Speed | Use Case |
|-------|------|-------|----------|
| `gemma3:12b` | ~8GB | Medium | Best quality (default) |
| `llama3.2:3b` | ~2GB | Fast | CPU-friendly alternative |

Pull your chosen model:
```bash
ollama pull gemma3:12b
```

### GPU Support

GPU acceleration is **auto-detected** — no configuration needed:

- **NVIDIA (CUDA)** — used automatically if available
- **Apple Silicon (MPS)** — used automatically on M1/M2/M3 Macs
- **CPU** — fully supported, just slower

For GPU-accelerated speech segmentation with pyannote.audio:
```bash
pip install recast[gpu]
```

## Verify Installation

```bash
recast --help
recast version
```
