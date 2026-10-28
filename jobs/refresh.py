"""Entry point for the daily refresh Job on Skydance Pages (command: python jobs/refresh.py).
See docs/WEBAPP.md. Sits at jobs/ in the app's source site, next to src/, config/, data/ and scripts/."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from promo_ops.refresh_job import main  # noqa: E402

raise SystemExit(main(["--source", str(ROOT), *sys.argv[1:]]))
