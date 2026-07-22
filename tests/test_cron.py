"""Unit tests for the minimal 5-field cron evaluator."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hubspot_agent import cron


def _dt(y=2026, mo=7, d=22, h=9, mi=30):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #

def test_validate_accepts_wildcards():
    cron.validate("* * * * *")


@pytest.mark.parametrize("expr", [
    "* * * *",            # too few fields
    "* * * * * *",        # too many fields
    "60 * * * *",         # minute out of range
    "* 24 * * *",         # hour out of range
    "* * 0 * *",          # day-of-month below 1
    "* * 32 * *",         # day-of-month above 31
    "* * * 13 *",         # month above 12
    "* * * * 8",          # day-of-week above 7
    "*/0 * * * *",        # zero step
    "*/-1 * * * *",       # negative step
    "*/x * * * *",        # non-int step
    "abc * * * *",        # non-int value
    "5-1 * * * *",        # reversed range
    "",                   # empty
])
def test_validate_rejects_junk(expr):
    with pytest.raises(ValueError):
        cron.validate(expr)


# --------------------------------------------------------------------------- #
# matches: each field form
# --------------------------------------------------------------------------- #

def test_matches_all_wildcards():
    assert cron.matches("* * * * *", _dt()) is True


def test_matches_single_integer_minute():
    assert cron.matches("30 * * * *", _dt(mi=30)) is True
    assert cron.matches("30 * * * *", _dt(mi=31)) is False


def test_matches_single_integer_hour():
    assert cron.matches("* 9 * * *", _dt(h=9)) is True
    assert cron.matches("* 9 * * *", _dt(h=10)) is False


def test_matches_comma_list():
    assert cron.matches("1,15,30 * * * *", _dt(mi=15)) is True
    assert cron.matches("1,15,30 * * * *", _dt(mi=16)) is False


def test_matches_range():
    # Mon-Fri at any time (2026-07-22 is a Wednesday)
    assert cron.matches("* * * * 1-5", _dt(d=22)) is True
    # 2026-07-25 is a Saturday
    assert cron.matches("* * * * 1-5", _dt(d=25)) is False


def test_matches_step_every_15_minutes():
    for mi in (0, 15, 30, 45):
        assert cron.matches("*/15 * * * *", _dt(mi=mi)) is True
    for mi in (1, 14, 16, 44):
        assert cron.matches("*/15 * * * *", _dt(mi=mi)) is False


def test_matches_bounded_step():
    # 0-30/10 -> {0, 10, 20, 30}
    for mi in (0, 10, 20, 30):
        assert cron.matches("0-30/10 * * * *", _dt(mi=mi)) is True
    for mi in (5, 40, 50):
        assert cron.matches("0-30/10 * * * *", _dt(mi=mi)) is False


def test_matches_month():
    assert cron.matches("* * * 7 *", _dt(mo=7)) is True
    assert cron.matches("* * * 7 *", _dt(mo=8)) is False


def test_dow_zero_is_sunday():
    # 2026-07-26 is a Sunday
    assert cron.matches("* * * * 0", _dt(d=26)) is True
    assert cron.matches("* * * * 0", _dt(d=27)) is False  # Monday


def test_dow_seven_also_sunday():
    assert cron.matches("* * * * 7", _dt(d=26)) is True
    assert cron.matches("* * * * 7", _dt(d=27)) is False


# --------------------------------------------------------------------------- #
# dom / dow OR-semantics
# --------------------------------------------------------------------------- #

def test_dom_and_dow_both_restricted_is_or():
    # "on the 1st OR on a Monday" — standard cron OR-semantics.
    # 2026-07-01 is a Wednesday: matches via dom.
    assert cron.matches("* * 1 * 1", _dt(d=1)) is True
    # 2026-07-20 is a Monday, not the 1st: matches via dow.
    assert cron.matches("* * 1 * 1", _dt(d=20)) is True
    # 2026-07-22 is a Wednesday, not the 1st: matches neither.
    assert cron.matches("* * 1 * 1", _dt(d=22)) is False


def test_dom_restricted_dow_wildcard_is_and():
    # dow is * so only dom constrains
    assert cron.matches("* * 22 * *", _dt(d=22)) is True
    assert cron.matches("* * 22 * *", _dt(d=23)) is False


# --------------------------------------------------------------------------- #
# is_due
# --------------------------------------------------------------------------- #

def test_is_due_none_last_run_uses_matches():
    assert cron.is_due("30 9 * * *", None, _dt(h=9, mi=30)) is True
    assert cron.is_due("30 9 * * *", None, _dt(h=9, mi=31)) is False


def test_is_due_catches_missed_tick_between_runs():
    # Daily 09:30. Last ran yesterday; now is 10:00 today — the 09:30 tick was
    # missed and must be caught.
    last = _dt(d=21, h=9, mi=30)
    now = _dt(d=22, h=10, mi=0)
    assert cron.is_due("30 9 * * *", last, now) is True


def test_is_due_false_when_no_tick_in_interval():
    # Daily 09:30. Last ran at 09:30, now 09:45 same day — no new tick.
    last = _dt(h=9, mi=30)
    now = _dt(h=9, mi=45)
    assert cron.is_due("30 9 * * *", last, now) is False


def test_is_due_excludes_last_run_minute_itself():
    # half-open (last_run, now]: a match exactly at last_run does not count.
    last = _dt(h=9, mi=30)
    now = _dt(h=9, mi=30)
    assert cron.is_due("30 9 * * *", last, now) is False


def test_is_due_includes_now_minute():
    last = _dt(h=9, mi=29)
    now = _dt(h=9, mi=30)
    assert cron.is_due("30 9 * * *", last, now) is True


def test_is_due_last_run_older_than_lookback_is_due():
    last = _dt(y=2024, mo=1, d=1, h=0, mi=0)
    now = _dt(y=2026, mo=7, d=22, h=9, mi=30)
    assert cron.is_due("30 9 * * *", last, now) is True


# --------------------------------------------------------------------------- #
# next_due
# --------------------------------------------------------------------------- #

def test_next_due_forward_scan():
    after = _dt(h=9, mi=30)
    nxt = cron.next_due("0 10 * * *", after)
    assert nxt == _dt(h=10, mi=0)


def test_next_due_is_strictly_after():
    after = _dt(h=10, mi=0)
    nxt = cron.next_due("0 10 * * *", after)
    # not the same minute — the next day's 10:00
    assert nxt == _dt(d=23, h=10, mi=0)


def test_next_due_none_when_unsatisfiable_within_cap():
    # Feb 30 never occurs.
    assert cron.next_due("0 0 30 2 *", _dt()) is None
