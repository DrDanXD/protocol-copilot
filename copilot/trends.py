"""What changed since the last visit, and what is moving the wrong way.

Pure arithmetic. No model involved, so every number here can be checked by hand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean

from .catalog import CATALOG
from .schema import Flag, Member, ValueStatus

CONFLICT_WINDOW_DAYS = 14
STALE_AFTER_DAYS = 180
WEARABLE_BASELINE = (90, 30)   # days before visit: from, to
WEARABLE_RECENT = 14           # last N days
WEARABLE_MIN_COVERAGE = 0.6


@dataclass
class AnalyteTrend:
    analyte: str
    series: list[tuple[date, float]]
    conflicted: bool = False
    unit_changed: bool = False

    @property
    def latest(self) -> float | None:
        return self.series[-1][1] if self.series else None

    @property
    def previous(self) -> float | None:
        return self.series[-2][1] if len(self.series) >= 2 else None

    @property
    def delta_pct(self) -> float | None:
        if self.latest is None or not self.previous:
            return None
        return (self.latest - self.previous) / self.previous * 100

    def monotonic_change_pct(self, draws: int, direction: str) -> float | None:
        """% change across the last `draws` values if every step moves the same way."""
        if len(self.series) < draws:
            return None
        vals = [v for _, v in self.series[-draws:]]
        steps = [b - a for a, b in zip(vals, vals[1:])]
        if direction == "up" and all(s > 0 for s in steps):
            return (vals[-1] - vals[0]) / vals[0] * 100
        if direction == "down" and all(s < 0 for s in steps):
            return (vals[0] - vals[-1]) / vals[0] * 100
        return None


@dataclass
class WearableTrend:
    metric: str
    baseline: float | None
    recent: float | None
    coverage_ok: bool

    @property
    def delta_pct(self) -> float | None:
        if not self.coverage_ok or not self.baseline or self.recent is None:
            return None
        return (self.recent - self.baseline) / self.baseline * 100


@dataclass
class TrendReport:
    analytes: dict[str, AnalyteTrend] = field(default_factory=dict)
    wearables: dict[str, WearableTrend] = field(default_factory=dict)
    flags: list[Flag] = field(default_factory=list)
    latest_draw_date: date | None = None
    latest_fasting: bool | None = None
    latest_values: dict[str, float] = field(default_factory=dict)


def analyse(member: Member) -> TrendReport:
    rep = TrendReport()
    draws = [d for d in member.sorted_draws() if d.collected != date.min]
    if not draws:
        rep.flags.append(Flag(kind="not_measured", message="No dated lab draws on file"))
        return rep
    latest = draws[-1]
    rep.latest_draw_date = latest.collected
    rep.latest_fasting = latest.fasting
    for v in latest.values:
        if v.usable:
            rep.latest_values[v.analyte] = v.value

    age_days = (member.visit_date - latest.collected).days
    if age_days > STALE_AFTER_DAYS:
        rep.flags.append(Flag(kind="stale", message=f"Latest labs are {age_days} days old. "
                                                     "Consider a new draw before changing the plan"))

    for d in draws:
        for v in d.values:
            if v.status in (ValueStatus.implausible, ValueStatus.missing_unit, ValueStatus.unknown_unit):
                if d is latest:
                    rep.flags.append(Flag(kind="implausible" if v.status == ValueStatus.implausible
                                          else "missing_unit", analyte=v.analyte,
                                          message=f"{v.raw_name} '{v.raw_value} {v.raw_unit}'".strip()
                                          + " held for review, not used"))
            if v.status == ValueStatus.unknown_analyte and d is latest:
                rep.flags.append(Flag(kind="unknown_analyte", analyte=v.analyte,
                                      message=f"'{v.raw_name}' is not in the catalog. Not used"))

    for aid, a in CATALOG.items():
        series, unit_changed = [], False
        for d in draws:
            v = d.get(aid)
            if v is None:
                continue
            if v.status == ValueStatus.incompatible_unit:
                unit_changed = True
                continue
            if v.usable:
                series.append((d.collected, v.value))
        if not series and not unit_changed:
            continue
        t = AnalyteTrend(aid, series, unit_changed=unit_changed)
        if unit_changed:
            rep.flags.append(Flag(kind="unit_change", analyte=aid,
                                  message=f"{a.display} was reported in a non-comparable unit in at "
                                          "least one draw (method change). Trend uses comparable draws only"))
        # conflict: two draws close in time that disagree beyond analytical tolerance
        for (d1, v1), (d2, v2) in zip(series, series[1:]):
            if (d2 - d1).days <= CONFLICT_WINDOW_DAYS:
                if abs(v2 - v1) / mean([v1, v2]) > 2 * a.tolerance:
                    t.conflicted = True
                    rep.flags.append(Flag(kind="conflict", analyte=aid,
                                          message=f"{a.display}: {v1:g} on {d1} vs {v2:g} on {d2}. "
                                                  "Too far apart for draws this close. Rules on this "
                                                  "marker paused until a retest"))
        rep.analytes[aid] = t

    for metric in ("hrv_rmssd", "resting_hr", "sleep_hours", "steps"):
        rep.wearables[metric] = _wearable_trend(member, metric)
    gaps = [m for m, w in rep.wearables.items() if not w.coverage_ok]
    if member.wearables and gaps:
        rep.flags.append(Flag(kind="wearable_gap", message="Not enough wearable data to judge a trend for: "
                                                           + ", ".join(gaps)))
    return rep


def _wearable_trend(member: Member, metric: str) -> WearableTrend:
    v = member.visit_date
    b_from, b_to = v - timedelta(days=WEARABLE_BASELINE[0]), v - timedelta(days=WEARABLE_BASELINE[1])
    r_from = v - timedelta(days=WEARABLE_RECENT)
    base = [getattr(w, metric) for w in member.wearables if b_from <= w.day < b_to]
    rec = [getattr(w, metric) for w in member.wearables if r_from <= w.day < v]
    base_ok = [x for x in base if x is not None]
    rec_ok = [x for x in rec if x is not None]
    need_b = (WEARABLE_BASELINE[0] - WEARABLE_BASELINE[1]) * WEARABLE_MIN_COVERAGE
    need_r = WEARABLE_RECENT * WEARABLE_MIN_COVERAGE
    ok = len(base_ok) >= need_b and len(rec_ok) >= need_r
    return WearableTrend(metric, round(mean(base_ok), 2) if base_ok else None,
                         round(mean(rec_ok), 2) if rec_ok else None, ok)


def what_changed(rep: TrendReport) -> list[str]:
    """Plain lines for the clinician: biggest moves since the previous draw."""
    lines = []
    moves = [(abs(t.delta_pct), aid, t) for aid, t in rep.analytes.items()
             if t.delta_pct is not None and not t.conflicted]
    for _, aid, t in sorted(moves, reverse=True):
        if abs(t.delta_pct) < 10:
            continue
        a = CATALOG[aid]
        lines.append(f"{a.display} {t.previous:g} → {t.latest:g} {a.unit} "
                     f"({t.delta_pct:+.0f}%) since {t.series[-2][0]}")
    for m, w in rep.wearables.items():
        if w.delta_pct is not None and abs(w.delta_pct) >= 10:
            label = {"hrv_rmssd": "HRV", "resting_hr": "Resting HR", "sleep_hours": "Sleep",
                     "steps": "Steps"}[m]
            lines.append(f"{label} {w.baseline:g} → {w.recent:g} ({w.delta_pct:+.0f}%) "
                         "last 14 days vs 1 to 3 months ago")
    return lines[:8]
