"""WSGI entrypoint for a real production server (gunicorn, etc).

    gunicorn --bind 0.0.0.0:8000 --workers 2 wsgi:app

`events web run` (Flask's dev server) is for local testing only — this is
the file a real deployment points at instead.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from events_tool.web import create_app  # noqa: E402

app = create_app()
