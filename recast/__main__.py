"""Entry point for python -m recast and PyInstaller bundles."""

import sys
import traceback

try:
    from recast.cli import app, _check_update_notification

    # Non-blocking update check (only for commands that aren't 'update' or 'version')
    if len(sys.argv) < 2 or sys.argv[1] not in ("update", "version", "--help"):
        _check_update_notification()

    app()
except Exception as e:
    print(f"Fatal error: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
