"""The shared look: a navy header bar with the Skydance logo (white SVG, inlined: nothing loaded from
outside) on every app page, with navigation, on top of the same content as before."""

from __future__ import annotations

import re

import pytest

from promo_ops import webapp
from test_webapp import call, make  # noqa: F401  (fixture)


@pytest.mark.parametrize("path", ["/", "/qa", "/review"])
def test_every_app_page_has_the_branded_header_with_the_logo_inline(make, path):
    srv, _, _ = make()
    html = call(srv, "GET", path)[2].decode()
    assert '<header class="top">' in html and 'class="logo"' in html and 'aria-label="Skydance"' in html
    assert "<svg" in html and "fill:#fff" in html.replace(" ", "") or "#fff" in html
    for label in ("Create an order", "Review a plan", "QA an order"):
        assert label in html.split("</header>")[0]
    assert not re.search(r'(?:src|href)="https?://', html.split("</header>")[0])      # nothing loaded from outside
    assert "<script src" not in html


def test_the_logo_files_are_clean_vectors():
    for name in ("skydance-white.svg", "skydance-black.svg"):
        s = (webapp.ASSETS / name).read_text(encoding="utf-8")
        assert s.lstrip().startswith("<svg") and "<script" not in s.lower() and "http://" not in s.replace("http://www.w3.org/2000/svg", "")
        assert len(s) < 20_000


def test_the_same_logos_ship_with_the_team_site():
    from promo_ops.config import REPO_ROOT
    for name in ("skydance-white.svg", "skydance-black.svg"):
        assert (REPO_ROOT / "site" / "logos" / name).read_text() == (webapp.ASSETS / name).read_text()
