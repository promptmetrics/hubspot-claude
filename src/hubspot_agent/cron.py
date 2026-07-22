"""Minimal 5-field cron evaluator (``minute hour day-of-month month day-of-week``).

An in-house evaluator (spec §7) covering the forms scheduled tasks need: ``*``,
single integers, comma lists, ranges, and steps.  No named months/days, no
special ``@`` shortcuts.  Day-of-week is 0-6 (0 = Sunday); ``7`` is also
accepted as Sunday.

All datetimes are timezone-aware UTC — callers pass ``now``; this module never
reads the wall clock.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple

# (lo, hi) inclusive bounds per field, in cron field order.
_FIELD_BOUNDS = [
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day-of-month
    (1, 12),  # month
    (0, 6),   # day-of-week (0 = Sunday)
]

# How far is_due / next_due scan before giving up (see docstrings).
_SCAN_CAP = timedelta(days=366)
_MINUTE = timedelta(minutes=1)


class _Compiled(NamedTuple):
    minutes: frozenset[int]
    hours: frozenset[int]
    doms: frozenset[int]
    months: frozenset[int]
    dows: frozenset[int]
    dom_restricted: bool
    dow_restricted: bool


def _parse_part(part: str, lo: int, hi: int, dow: bool) -> set[int]:
    part = part.strip()
    if not part:
        raise ValueError("empty field component")
    step = 1
    base = part
    if "/" in part:
        base, _, step_s = part.partition("/")
        try:
            step = int(step_s)
        except ValueError:
            raise ValueError(f"invalid step {step_s!r} in {part!r}")
        if step <= 0:
            raise ValueError(f"step must be positive in {part!r}")
        base = base.strip()

    # Day-of-week accepts 7 (Sunday) as input; normalize to 0 after expansion.
    hi_in = 7 if dow else hi

    if base == "*":
        start, end = lo, hi_in
    elif "-" in base:
        a, _, b = base.partition("-")
        start, end = _int(a), _int(b)
    else:
        start = _int(base)
        # A bare "N/S" runs from N to the top of the range.
        end = hi_in if "/" in part else start

    if start < lo or end > hi_in or start > end:
        raise ValueError(f"value out of range in {part!r} (allowed {lo}-{hi_in})")

    values = set(range(start, end + 1, step))
    if dow:
        values = {0 if v == 7 else v for v in values}
    return values


def _int(token: str) -> int:
    token = token.strip()
    try:
        return int(token)
    except ValueError:
        raise ValueError(f"expected an integer, got {token!r}")


def _parse_field(field: str, lo: int, hi: int, dow: bool = False) -> frozenset[int]:
    values: set[int] = set()
    for part in field.split(","):
        values |= _parse_part(part, lo, hi, dow)
    return frozenset(values)


def _compile(expr: str) -> _Compiled:
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"expected 5 cron fields, got {len(fields)}: {expr!r}")
    minute_f, hour_f, dom_f, month_f, dow_f = fields
    (mlo, mhi), (hlo, hhi), (dlo, dhi), (molo, mohi), (wlo, whi) = _FIELD_BOUNDS
    return _Compiled(
        minutes=_parse_field(minute_f, mlo, mhi),
        hours=_parse_field(hour_f, hlo, hhi),
        doms=_parse_field(dom_f, dlo, dhi),
        months=_parse_field(month_f, molo, mohi),
        dows=_parse_field(dow_f, wlo, whi, dow=True),
        dom_restricted=dom_f.strip() != "*",
        dow_restricted=dow_f.strip() != "*",
    )


def validate(expr: str) -> None:
    """Raise ``ValueError`` if ``expr`` is not a well-formed 5-field cron."""
    _compile(expr)


def _matches_compiled(c: _Compiled, dt: datetime) -> bool:
    if dt.minute not in c.minutes:
        return False
    if dt.hour not in c.hours:
        return False
    if dt.month not in c.months:
        return False
    # cron day-of-week: Sunday=0..Saturday=6; datetime.weekday(): Monday=0..Sunday=6.
    cron_dow = (dt.weekday() + 1) % 7
    dom_match = dt.day in c.doms
    dow_match = cron_dow in c.dows
    # Standard cron: when both day fields are restricted the run fires if EITHER
    # matches; otherwise the wildcard field is trivially true and it's an AND.
    if c.dom_restricted and c.dow_restricted:
        return dom_match or dow_match
    return dom_match and dow_match


def matches(expr: str, dt: datetime) -> bool:
    """Return True if the UTC datetime ``dt`` satisfies ``expr`` (minute resolution)."""
    return _matches_compiled(_compile(expr), dt)


def is_due(expr: str, last_run: datetime | None, now: datetime) -> bool:
    """True if a cron-matching minute falls in the half-open interval ``(last_run, now]``.

    With ``last_run is None`` this reduces to ``matches(expr, now)``.  Otherwise
    minute-truncated candidates are walked forward from just after ``last_run``;
    the scan is capped at ~366 days, and a ``last_run`` older than that is
    treated as due (a missed tick is assumed rather than scanned for).
    """
    c = _compile(expr)
    if last_run is None:
        return _matches_compiled(c, now)

    now_m = now.replace(second=0, microsecond=0)
    if last_run < now_m - _SCAN_CAP:
        return True

    candidate = last_run.replace(second=0, microsecond=0) + _MINUTE
    while candidate <= now_m:
        if _matches_compiled(c, candidate):
            return True
        candidate += _MINUTE
    return False


def next_due(expr: str, after: datetime) -> datetime | None:
    """Return the next matching minute strictly after ``after``, or None.

    Scans forward at minute resolution, capped at ~366 days (returns None if no
    match occurs within the cap, e.g. an impossible date like Feb 30).
    """
    c = _compile(expr)
    limit = after + _SCAN_CAP
    candidate = after.replace(second=0, microsecond=0) + _MINUTE
    while candidate <= limit:
        if _matches_compiled(c, candidate):
            return candidate
        candidate += _MINUTE
    return None
