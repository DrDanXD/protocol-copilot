"""The test set: tricky cases with a clear pass rule each.

Every case states what a careful clinician would expect: which rules must fire,
which must not, which flags must appear, and whether the member summary must
be held. `run_evals.py` scores them and writes RESULTS.md.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from copilot.extract import build_draw, validate_row
from copilot.schema import Member, WearableDay
from copilot.synth import wearable_series

VISIT = date(2026, 11, 2)


@dataclass
class Case:
    id: str
    group: str
    title: str
    member: Callable[[], Member]
    fires: set[str] = field(default_factory=set)
    not_fires: set[str] = field(default_factory=set)
    flags: set[str] = field(default_factory=set)
    no_flags: set[str] = field(default_factory=set)
    status: str = "draft"
    member_blocked: bool | None = None
    check: Callable | None = None   # extra assertion: (member, plan, summary) -> str | None


def mk(draws: list[tuple[int, dict, bool | None]], wear: list[WearableDay] | None = None) -> Member:
    """draws: (days before visit, {analyte_name: value or (value, unit)}, fasting)."""
    out = []
    for k, (days, vals, fasting) in enumerate(draws):
        rows = []
        for name, v in vals.items():
            val, unit = (v if isinstance(v, tuple) else (v, None))
            if unit is None:
                from copilot.catalog import lookup
                unit = lookup(name).unit
            rows.append({"name": name, "val": str(val), "unit": unit, "flag": ""})
        out.append(build_draw(rows, VISIT - timedelta(days=days), f"D{k}", "case", fasting))
    return Member(member_id="CASE", first_name="Alex", age=48, sex="F", visit_date=VISIT,
                  draws=out, wearables=wear or [])


def wear(**kw) -> list[WearableDay]:
    return wearable_series(VISIT - timedelta(days=90), 90, random.Random(3), **kw)


def short_sleep() -> list[WearableDay]:
    w = wear()
    for d in w:
        if d.sleep_hours is not None:
            d.sleep_hours = round(d.sleep_hours - 1.1, 2)
    return w


NORMAL = {"apob": 80, "a1c": 5.2, "glucose": 88, "hscrp": 0.6, "vitd": 40, "potassium": 4.3,
          "sodium": 140, "hgb": 14, "egfr": 95, "alt": 22, "tsh": 1.6, "ferritin": 110, "tg": 100}


def panel(**over) -> dict:
    p = dict(NORMAL)
    p.update(over)
    return p


def _max3(m, plan, s):
    if len(s.next_steps) > 3:
        return f"{len(s.next_steps)} next steps, limit is 3"
    return None


def _headline(text):
    def f(m, plan, s):
        return None if text in s.headline else f"headline was '{s.headline}'"
    return f


def _after_contact(m, plan, s):
    from copilot.member import member_summary
    if not s.blocked:
        return "summary released before contact was logged"
    after = member_summary(plan, first_name=m.first_name, contacted=True)
    text = " ".join([after.headline, *after.body])
    if after.blocked or "steady" in text.lower():
        return f"after contact: '{text}'"
    return None


CASES: list[Case] = [
    # ---------- critical values ----------
    Case("C01", "critical", "Potassium 6.4 blocks the member summary",
         lambda: mk([(5, panel(potassium=6.4), True)]), flags={"critical"},
         status="blocked_critical", member_blocked=True),
    Case("C02", "critical", "Potassium 2.7 blocks the member summary",
         lambda: mk([(5, panel(potassium=2.7), True)]), flags={"critical"},
         status="blocked_critical", member_blocked=True),
    Case("C03", "critical", "Glucose 420 is critical",
         lambda: mk([(5, panel(glucose=420), True)]), flags={"critical"},
         status="blocked_critical", member_blocked=True, not_fires={"GLY-03"}),
    Case("C04", "critical", "Sodium 121 is critical",
         lambda: mk([(5, panel(sodium=121), True)]), flags={"critical"}, status="blocked_critical"),
    Case("C05", "critical", "Hemoglobin 6.5 is critical",
         lambda: mk([(5, panel(hgb=6.5), True)]), flags={"critical"}, status="blocked_critical"),
    Case("C06", "critical", "Critical value hidden behind a unit: glucose 2.5 mmol/L",
         lambda: mk([(5, panel(glucose=(2.5, "mmol/L")), True)]), flags={"critical"},
         status="blocked_critical"),
    Case("C07", "critical", "Potassium 5.9 is high but not critical",
         lambda: mk([(5, panel(potassium=5.9), True)]), no_flags={"critical"}, status="draft",
         member_blocked=False),
    Case("C08", "critical", "Critical value in an old draw only does not block today",
         lambda: mk([(200, panel(potassium=6.5), True), (5, panel(), True)]),
         no_flags={"critical"}, status="draft"),
    Case("C09", "critical", "Typo 45 mmol/L potassium is held, not treated as critical",
         lambda: mk([(5, panel(potassium=45), True)]), flags={"implausible"},
         no_flags={"critical"}, status="draft"),
    Case("C10", "critical", "Critical beats conflict: K 6.5 days after K 4.2 still blocks",
         lambda: mk([(10, panel(potassium=4.2), True), (3, panel(potassium=6.5), True)]),
         flags={"critical", "conflict"}, status="blocked_critical", member_blocked=True),

    # ---------- conflicting data ----------
    Case("K01", "conflict", "ApoB 95 then 140 ten days apart pauses lipid rules",
         lambda: mk([(12, panel(apob=95), True), (2, panel(apob=140), True)]),
         flags={"conflict"}, fires={"RETEST-apob"}, not_fires={"LIPID-01", "LIPID-03"}),
    Case("K02", "conflict", "A1c 5.4 then 6.6 a week apart pauses glucose rules",
         lambda: mk([(9, panel(a1c=5.4), True), (2, panel(a1c=6.6), True)]),
         flags={"conflict"}, fires={"RETEST-a1c"}, not_fires={"GLY-02", "GLY-01"}),
    Case("K03", "conflict", "Close draws within assay tolerance are not a conflict",
         lambda: mk([(10, panel(apob=100), True), (2, panel(apob=104), True)]),
         no_flags={"conflict"}, fires={"LIPID-02"}),
    Case("K04", "conflict", "Big change over four months is a trend, not a conflict",
         lambda: mk([(120, panel(apob=100), True), (2, panel(apob=125), True)]),
         no_flags={"conflict"}, fires={"LIPID-03", "LIPID-02"}),

    # ---------- fasting ----------
    Case("F01", "fasting", "Glucose 110 on a non-fasting draw does not fire",
         lambda: mk([(5, panel(glucose=110), False)]), not_fires={"GLY-03"}),
    Case("F02", "fasting", "Glucose 110 on a fasting draw fires",
         lambda: mk([(5, panel(glucose=110), True)]), fires={"GLY-03"}),
    Case("F03", "fasting", "Fasting status unknown does not fire",
         lambda: mk([(5, panel(glucose=110), None)]), not_fires={"GLY-03"}),

    # ---------- units and methods ----------
    Case("U01", "units", "Lp(a) in mg/dL cannot be compared to an nmol/L threshold",
         lambda: mk([(5, panel(**{"lpa": (150, "mg/dL")}), True)]),
         flags={"unit_change"}, not_fires={"LIPID-04"}),
    Case("U02", "units", "Lp(a) switched from nmol/L to mg/dL between draws",
         lambda: mk([(150, panel(lpa=140), True), (5, panel(**{"lpa": (60, "mg/dL")}), True)]),
         flags={"unit_change"}, not_fires={"LIPID-04"}),
    Case("U03", "units", "Glucose 6.1 mmol/L converts to about 110 mg/dL and fires",
         lambda: mk([(5, panel(glucose=(6.1, "mmol/L")), True)]), fires={"GLY-03"}),
    Case("U04", "units", "ApoB 1.4 g/L converts to 140 mg/dL",
         lambda: mk([(5, panel(apob=(1.4, "g/L")), True)]), fires={"LIPID-01"}),
    Case("U05", "units", "Vitamin D 40 nmol/L converts to about 16 ng/mL",
         lambda: mk([(5, panel(vitd=(40, "nmol/L")), True)]), fires={"VITD-01"}),
    Case("U06", "units", "ApoB with no unit printed is held, not used",
         lambda: mk([(5, panel(apob=(140, "")), True)]), flags={"missing_unit"},
         not_fires={"LIPID-01"}),
    Case("U07", "units", "Unknown test name is flagged and ignored",
         lambda: mk([(5, {**panel(), "Mystery Marker": (3, "U/L")}, True)]),
         flags={"unknown_analyte"}),

    # ---------- missing and stale ----------
    Case("M01", "missing", "No ApoB measured means no lipid rules and no crash",
         lambda: mk([(5, {k: v for k, v in panel().items() if k != "apob"}, True)]),
         not_fires={"LIPID-01", "LIPID-02", "LIPID-03"}),
    Case("M02", "missing", "Labs 300 days old are flagged stale",
         lambda: mk([(300, panel(), True)]), flags={"stale"}),
    Case("M03", "missing", "No draws at all: no summary claims results look fine",
         lambda: mk([]), flags={"not_measured"}, member_blocked=True),
    Case("M04", "missing", "Marker only in an older draw does not fire on today's plan",
         lambda: mk([(150, panel(apob=150), True), (5, {k: v for k, v in panel().items() if k != "apob"}, True)]),
         not_fires={"LIPID-01"}),

    # ---------- thresholds ----------
    Case("B01", "boundary", "A1c exactly 5.7 fires the 5.7 to 6.4 rule",
         lambda: mk([(5, panel(a1c=5.7), True)]), fires={"GLY-01"}, not_fires={"GLY-02"}),
    Case("B02", "boundary", "A1c 6.45 falls in no gap between rules",
         lambda: mk([(5, panel(a1c=6.45), True)]), fires={"GLY-01"}, not_fires={"GLY-02"}),
    Case("B03", "boundary", "A1c 6.5 moves to the confirm-by-repeat rule",
         lambda: mk([(5, panel(a1c=6.5), True)]), fires={"GLY-02"}, not_fires={"GLY-01"}),
    Case("B04", "boundary", "ApoB exactly 130 is the discuss rule, not the lifestyle rule",
         lambda: mk([(5, panel(apob=130), True)]), fires={"LIPID-01"}, not_fires={"LIPID-02"}),
    Case("B05", "boundary", "ApoB exactly 90 fires nothing",
         lambda: mk([(5, panel(apob=90), True)]), not_fires={"LIPID-01", "LIPID-02"}),
    Case("B06", "boundary", "hs-CRP 12 is the acute rule, not the routine repeat",
         lambda: mk([(5, panel(hscrp=12), True)]), fires={"INF-02"}, not_fires={"INF-01"}),
    Case("B07", "boundary", "Vitamin D 29.95 falls in no gap between rules",
         lambda: mk([(5, panel(vitd=29.95), True)]), fires={"VITD-02"}),
    Case("B08", "boundary", "Fasting glucose 125.5 still in the 100 to 125 band",
         lambda: mk([(5, panel(glucose=125.5), True)]), fires={"GLY-03"}),

    # ---------- wearables ----------
    Case("W01", "wearable", "HRV down 20% and resting HR up fires recovery",
         lambda: mk([(5, panel(), True)], wear(hrv_drift=-24, rhr_drift=8)), fires={"REC-01"}),
    Case("W02", "wearable", "HRV down but resting HR flat does not fire",
         lambda: mk([(5, panel(), True)], wear(hrv_drift=-24)), not_fires={"REC-01"}),
    Case("W03", "wearable", "Big gap in wearable data blocks the trend",
         lambda: mk([(5, panel(), True)], wear(hrv_drift=-24, rhr_drift=8, gap=(5, 55))),
         flags={"wearable_gap"}, not_fires={"REC-01"}),
    Case("W04", "wearable", "Average sleep about 6 hours fires sleep rule",
         lambda: mk([(5, panel(), True)], short_sleep()), fires={"SLP-01"}),
    Case("W05", "wearable", "No wearable linked: no noise, no rule",
         lambda: mk([(5, panel(), True)]), no_flags={"wearable_gap"}, not_fires={"REC-01", "SLP-01"}),

    # ---------- member-facing ----------
    Case("P01", "member", "Five rules firing still gives at most 3 calm next steps",
         lambda: mk([(120, panel(apob=110), True),
                     (5, panel(apob=140, a1c=6.0, hscrp=5, vitd=15, alt=60), True)]),
         fires={"LIPID-01", "GLY-01", "INF-01", "VITD-01", "LIV-01"}, member_blocked=False,
         check=_max3),
    Case("P02", "member", "Improving member gets a positive headline",
         lambda: mk([(120, panel(apob=110), True), (5, panel(apob=85), True)]),
         fires={"LIPID-06"}, member_blocked=False, check=_headline("Good progress")),
    Case("P04", "member", "After the call for a critical value, the summary never says steady",
         lambda: mk([(5, panel(potassium=6.4), True)]), status="blocked_critical",
         check=_after_contact),
    Case("P03", "member", "All normal: steady headline, nothing to do",
         lambda: mk([(5, panel(), True)]), member_blocked=False, check=_headline("steady")),
]
