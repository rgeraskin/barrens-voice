"""Barrens Voice: the launcher window (pythonw runs a .pyw without a console). See bv/launcher/app.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bv.launcher.app import main  # noqa: E402

sys.exit(main())
