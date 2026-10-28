"""./ship.sh: one command to run the tests, push to GitHub (both places) and publish the app.
It stops at the first problem and never publishes anything that didn't pass or wasn't pushed."""

from __future__ import annotations

import importlib.util
import sys

import pytest

from promo_ops.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location("ship", REPO_ROOT / "scripts" / "ship.py")
ship = importlib.util.module_from_spec(_spec)
sys.modules["ship"] = ship
_spec.loader.exec_module(ship)


class Runner:
    """Fake command runner: records commands, answers from a script of (substring -> (rc, output))."""

    def __init__(self, answers=None):
        self.cmds, self.answers = [], answers or {}

    def __call__(self, cmd):
        text = " ".join(map(str, cmd))
        self.cmds.append(text)
        for key, res in self.answers.items():
            if key in text:
                return res
        return 0, ""

    def ran(self, part):
        return any(part in c for c in self.cmds)


def go(runner, **kw):
    return ship.ship(run=runner, log=lambda *_: None, **kw)


def test_the_happy_path_runs_tests_then_pushes_both_then_publishes_in_order():
    r = Runner({"git remote": (0, "origin\npersonal\n"), "git status": (0, "")})
    assert go(r) == 0
    order = [i for i, c in enumerate(r.cmds) if "pytest" in c or "push origin" in c or "push personal" in c
             or "publish_site.py --app" in c]
    assert [("pytest" in r.cmds[i], "push origin" in r.cmds[i], "push personal" in r.cmds[i]) for i in order[:3]] == \
        [(True, False, False), (False, True, False), (False, False, True)]
    assert "publish_site.py --app" in r.cmds[order[3]]
    assert any("HEAD:main" in c for c in r.cmds)


def test_unsaved_code_changes_stop_it_before_anything_runs():
    r = Runner({"git status": (0, " M src/promo_ops/qa.py\n?? tests/test_new.py\n")})
    assert go(r) == 1
    assert not r.ran("pytest") and not r.ran("push") and not r.ran("publish")


def test_regenerated_data_files_do_not_count_as_unsaved_work():
    status = (" M data/series/synced_series.csv\n M templates/targeting-options/shows.csv\n"
              " M templates/campaign-plan/campaign-plan-form.html\n?? logs/new.log\n")
    r = Runner({"git status": (0, status), "git remote": (0, "origin\n")})
    assert go(r) == 0


def test_failing_tests_stop_everything():
    r = Runner({"pytest": (1, "1 failed"), "git status": (0, "")})
    assert go(r) == 1
    assert not r.ran("push") and not r.ran("publish")


def test_a_failed_push_stops_before_publishing():
    r = Runner({"push origin": (1, "rejected"), "git remote": (0, "origin\n"), "git status": (0, "")})
    assert go(r) == 1
    assert not r.ran("publish")


def test_a_missing_backup_remote_is_skipped_not_fatal():
    r = Runner({"git remote": (0, "origin\n"), "git status": (0, "")})
    assert go(r) == 0 and not r.ran("push personal")


def test_skip_tests_is_explicit_and_still_pushes_and_publishes():
    r = Runner({"git status": (0, ""), "git remote": (0, "origin\n")})
    assert go(r, skip_tests=True) == 0
    assert not r.ran("pytest") and r.ran("push origin") and r.ran("publish_site.py --app")


def test_dry_run_changes_nothing():
    r = Runner({"git status": (0, ""), "git remote": (0, "origin\npersonal\n")})
    assert go(r, dry_run=True) == 0
    assert not r.ran("push") and not r.ran("pytest") and not r.ran("publish_site.py --app")


def test_a_failed_publish_is_reported_as_a_failure():
    r = Runner({"publish_site.py --app": (1, "VPN off?"), "git status": (0, ""), "git remote": (0, "origin\n")})
    assert go(r, skip_tests=True) == 1
