"""Entry point for python -m recast and PyInstaller bundles."""

import sys
import traceback

try:
    from recast.cli import app
    app()
except Exception as e:
    print(f"Fatal error: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
