"""Entry point for the hosted team app (Skydance Pages runs `python app.py`; see docs/WEBAPP.md).

The app site holds this file at its top, next to src/, config/, data/ and templates/, which is the
same layout as the repo -- so the code finds its config and data exactly as it does on a laptop."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
os.environ.setdefault("PROMO_WEBAPP_HOST", "0.0.0.0")          # Pages hands the port in $PORT

from promo_ops.webapp import main  # noqa: E402

raise SystemExit(main())
