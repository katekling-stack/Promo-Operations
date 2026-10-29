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


import pytest as _pytest

SITE_PAGES = ["index.html", "create-an-order.html", "qa-checklist.html", "setup-guide.html"]


@_pytest.mark.parametrize("page", SITE_PAGES)
def test_every_team_site_page_has_the_logo_and_the_brand_header(page):
    from promo_ops.config import REPO_ROOT
    html = (REPO_ROOT / "site" / page).read_text(encoding="utf-8")
    assert 'src="logos/skydance-white.svg"' in html and 'alt="Skydance"' in html
    assert "#12123F" in html and "linear-gradient(135deg,#0A1730" not in html


def test_the_form_header_carries_the_logo_as_embedded_data_and_the_brand_colors():
    from promo_ops.config import REPO_ROOT
    form = (REPO_ROOT / "templates" / "campaign-plan" / "campaign-plan-form.html").read_text(encoding="utf-8")
    assert 'class="hlogo"' in form and 'src="data:image/svg+xml;base64,' in form
    assert "--navy:#12123F" in form and "#0B3D91" not in form
    assert "LOGO_DATA_URI_PLACEHOLDER" not in form
