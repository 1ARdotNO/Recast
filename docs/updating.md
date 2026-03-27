# Updating Recast

## Auto-Update (Standalone Binary)

Recast includes a built-in auto-updater for standalone binaries.

### Check for Updates

```bash
recast update --check
```

Output:
```
Current version: v0.1.3
Checking for updates...
New version available: v0.2.0
Release: https://github.com/1ARdotNO/Recast/releases/tag/v0.2.0
```

### Install Update

```bash
recast update
```

This will:

1. Check GitHub Releases for the latest version
2. Download the binary for your platform
3. Verify file integrity (SHA256 + size check)
4. Replace the current binary
5. Prompt to restart

For non-interactive use (e.g. scripts):

```bash
recast update --yes
```

### Startup Notification

When you run any Recast command, it silently checks for updates and shows a notification if one is available:

```
Update available: v0.2.0 (current: v0.1.3). Run 'recast update' to install.
```

This check is non-blocking and won't slow down your command.

## Manual Update (Standalone Binary)

1. Download the latest binary from [GitHub Releases](https://github.com/1ARdotNO/Recast/releases/latest)
2. Replace your existing binary:

=== "macOS/Linux"

    ```bash
    chmod +x recast-macos-arm64
    sudo mv recast-macos-arm64 /usr/local/bin/recast
    ```

=== "Windows"

    Replace `recast-windows-x86_64.exe` in your installation directory.

## Update from Source

If you installed from source with pip:

```bash
cd Recast
git pull
pip install -e ".[dev]"
```

## Version History

Check the [releases page](https://github.com/1ARdotNO/Recast/releases) for changelog and all versions.
