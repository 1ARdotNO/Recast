"""Tests for auto-updater."""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from recast.updater import (
    check_for_update,
    compute_sha256,
    verify_download,
    _parse_version,
    _get_asset_name,
    download_update,
    install_update,
)


MOCK_RELEASE = {
    "tag_name": "v0.2.0",
    "html_url": "https://github.com/1ARdotNO/Recast/releases/tag/v0.2.0",
    "assets": [
        {
            "name": "recast-linux-x86_64",
            "browser_download_url": "https://github.com/1ARdotNO/Recast/releases/download/v0.2.0/recast-linux-x86_64",
            "size": 50000000,
        },
        {
            "name": "recast-macos-arm64",
            "browser_download_url": "https://github.com/1ARdotNO/Recast/releases/download/v0.2.0/recast-macos-arm64",
            "size": 73000000,
        },
        {
            "name": "recast-windows-x86_64.exe",
            "browser_download_url": "https://github.com/1ARdotNO/Recast/releases/download/v0.2.0/recast-windows-x86_64.exe",
            "size": 80000000,
        },
    ],
}


class TestParseVersion:
    def test_basic(self):
        assert _parse_version("0.1.3") == (0, 1, 3)

    def test_with_v(self):
        assert _parse_version("v0.1.3") == (0, 1, 3)

    def test_comparison(self):
        assert _parse_version("v0.2.0") > _parse_version("v0.1.3")
        assert _parse_version("v0.1.3") == _parse_version("0.1.3")
        assert _parse_version("v1.0.0") > _parse_version("v0.99.99")

    def test_invalid(self):
        assert _parse_version("invalid") == (0, 0, 0)


class TestGetAssetName:
    def test_returns_string(self):
        name = _get_asset_name()
        assert "recast" in name


class TestComputeSha256:
    def test_known_content(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        sha = compute_sha256(f)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert sha == expected

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        sha = compute_sha256(f)
        assert len(sha) == 64  # SHA256 hex digest length


class TestCheckForUpdate:
    def test_no_update_when_current(self):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {**MOCK_RELEASE, "tag_name": "v0.1.3"}
        ).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = check_for_update("0.1.3")
            assert result is None

    def test_update_available(self):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(MOCK_RELEASE).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = check_for_update("0.1.3")
            assert result is not None
            assert result["latest_version"] == "v0.2.0"
            assert "download_url" in result

    def test_network_error_returns_none(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = check_for_update("0.1.3")
            assert result is None


class TestVerifyDownload:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "binary"
        f.write_bytes(b"\x00" * 1000)
        sha = verify_download(f, expected_size=1000)
        assert len(sha) == 64

    def test_size_mismatch(self, tmp_path):
        f = tmp_path / "binary"
        f.write_bytes(b"\x00" * 100)
        with pytest.raises(RuntimeError, match="Size mismatch"):
            verify_download(f, expected_size=50000)


class TestDownloadUpdate:
    def test_download(self, tmp_path):
        update_info = {
            "download_url": "https://example.com/recast",
            "asset_name": "recast-test-binary",
            "asset_size": 100,
        }

        def fake_retrieve(url, dest):
            Path(dest).write_bytes(b"\x00" * 100)

        with patch("urllib.request.urlretrieve", side_effect=fake_retrieve):
            path = download_update(update_info, dest_dir=tmp_path)
            assert path.exists()
            assert path.name == "recast-test-binary"


class TestInstallUpdate:
    def test_not_frozen_raises(self, tmp_path):
        downloaded = tmp_path / "new_binary"
        downloaded.write_bytes(b"\x00" * 100)

        with patch("sys.frozen", False, create=True):
            with pytest.raises(RuntimeError, match="standalone"):
                install_update(downloaded)


class TestCLIUpdateCommand:
    def test_version_command(self):
        from typer.testing import CliRunner
        from recast.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "recast v" in result.output

    def test_update_check_only(self):
        from typer.testing import CliRunner
        from recast.cli import app

        with patch("recast.updater.check_for_update", return_value=None):
            runner = CliRunner()
            result = runner.invoke(app, ["update", "--check"])
            assert result.exit_code == 0
            assert "latest version" in result.output

    def test_update_available_check(self):
        from typer.testing import CliRunner
        from recast.cli import app

        update_info = {
            "current_version": "0.1.3",
            "latest_version": "v0.2.0",
            "download_url": "https://example.com/recast",
            "asset_name": "recast-test",
            "asset_size": 100,
            "release_url": "https://github.com/1ARdotNO/Recast/releases/tag/v0.2.0",
        }

        with patch("recast.updater.check_for_update", return_value=update_info):
            runner = CliRunner()
            result = runner.invoke(app, ["update", "--check"])
            assert result.exit_code == 0
            assert "v0.2.0" in result.output
