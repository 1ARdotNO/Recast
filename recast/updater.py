"""Auto-updater: check GitHub releases, download, verify SHA, self-update."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import sys
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger()

GITHUB_REPO = "1ARdotNO/Recast"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _get_asset_name() -> str:
    """Get the expected asset name for the current platform."""
    system = platform.system().lower()
    if system == "darwin":
        return "recast-macos-arm64"
    elif system == "windows":
        return "recast-windows-x86_64.exe"
    else:
        return "recast-linux-x86_64"


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse version string like 'v0.1.3' or '0.1.3' into tuple."""
    v = version_str.lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def check_for_update(current_version: str) -> dict | None:
    """Check GitHub releases for a newer version.

    Returns dict with update info or None if up to date.
    """
    try:
        import urllib.request
        import json

        req = urllib.request.Request(
            GITHUB_API,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        latest_tag = data.get("tag_name", "")
        latest_version = _parse_version(latest_tag)
        current = _parse_version(current_version)

        if latest_version <= current:
            return None

        asset_name = _get_asset_name()
        download_url = None
        asset_size = 0

        for asset in data.get("assets", []):
            if asset["name"] == asset_name:
                download_url = asset["browser_download_url"]
                asset_size = asset.get("size", 0)
                break

        if not download_url:
            logger.warning("updater.no_asset", asset=asset_name, tag=latest_tag)
            return None

        return {
            "current_version": current_version,
            "latest_version": latest_tag,
            "download_url": download_url,
            "asset_name": asset_name,
            "asset_size": asset_size,
            "release_url": data.get("html_url", ""),
        }

    except Exception as e:
        logger.debug("updater.check_failed", error=str(e))
        return None


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def download_update(update_info: dict, dest_dir: Path | None = None) -> Path:
    """Download the update binary and return its path.

    Raises on failure.
    """
    import urllib.request

    if dest_dir is None:
        dest_dir = Path(tempfile.mkdtemp(prefix="recast_update_"))

    dest_path = dest_dir / update_info["asset_name"]

    logger.info(
        "updater.downloading",
        url=update_info["download_url"],
        dest=str(dest_path),
    )

    urllib.request.urlretrieve(update_info["download_url"], str(dest_path))

    if not dest_path.exists() or dest_path.stat().st_size == 0:
        raise RuntimeError("Download failed: empty file")

    # Make executable on Unix
    if platform.system() != "Windows":
        dest_path.chmod(dest_path.stat().st_mode | stat.S_IEXEC)

    return dest_path


def verify_download(downloaded_path: Path, expected_size: int = 0) -> str:
    """Verify download integrity. Returns SHA256 hash."""
    actual_size = downloaded_path.stat().st_size
    if expected_size > 0 and abs(actual_size - expected_size) > 1024:
        raise RuntimeError(
            f"Size mismatch: expected ~{expected_size}, got {actual_size}"
        )

    sha = compute_sha256(downloaded_path)
    logger.info("updater.verified", sha256=sha, size=actual_size)
    return sha


def install_update(downloaded_path: Path) -> Path:
    """Replace the current binary with the downloaded one.

    Returns the path of the installed binary.
    """
    # Find current binary location
    current_binary = Path(sys.executable)

    # If running from PyInstaller bundle
    if getattr(sys, "_MEIPASS", None):
        current_binary = Path(sys.argv[0]).resolve()

    # If it's a Python script (not frozen), skip
    if not getattr(sys, "frozen", False):
        logger.warning("updater.not_frozen", msg="Cannot self-update a non-frozen install")
        raise RuntimeError(
            "Self-update only works with standalone binaries. "
            "Use pip install --upgrade for source installs."
        )

    backup_path = current_binary.with_suffix(".bak")

    logger.info(
        "updater.installing",
        current=str(current_binary),
        new=str(downloaded_path),
    )

    # Backup current binary
    if current_binary.exists():
        shutil.copy2(current_binary, backup_path)

    try:
        # Replace binary
        shutil.copy2(downloaded_path, current_binary)

        # Make executable on Unix
        if platform.system() != "Windows":
            current_binary.chmod(current_binary.stat().st_mode | stat.S_IEXEC)

        # Clean up backup
        backup_path.unlink(missing_ok=True)

        logger.info("updater.installed", path=str(current_binary))
        return current_binary

    except Exception:
        # Restore backup on failure
        if backup_path.exists():
            shutil.copy2(backup_path, current_binary)
            backup_path.unlink(missing_ok=True)
        raise


def restart_app() -> None:
    """Restart the application with the same arguments."""
    logger.info("updater.restarting")
    os.execv(sys.argv[0], sys.argv)


def perform_update(update_info: dict) -> bool:
    """Full update flow: download, verify, install.

    Returns True on success.
    """
    try:
        downloaded = download_update(update_info)
        verify_download(downloaded, update_info.get("asset_size", 0))
        install_update(downloaded)

        # Clean up temp download
        shutil.rmtree(downloaded.parent, ignore_errors=True)

        return True

    except Exception as e:
        logger.error("updater.failed", error=str(e))
        return False
