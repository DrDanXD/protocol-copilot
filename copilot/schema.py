"""Data model shared by every stage of the pipeline.

Kept deliberately close to what Retention Radar uses for a member, so the two
tools can share one member record in a clinic.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ValueStatus(str, Enum):
    ok = "ok"
    converted = "converted"
    implausible = "implausible"          # outside the physically plausible window
    missing_unit = "missing_unit"
    unknown_unit = "unknown_unit"
    incompatible_unit = "incompatible_unit"  # e.g. Lp(a) mg/dL vs nmol/L
    unknown_analyte = "unknown_analyte"


class LabValue(BaseModel):
    analyte: str                       # catalog id, or raw name if unknown
    raw_name: str
    raw_value: str
    raw_unit: str = ""
    value: float | None = None         # canonical unit, None if unusable
    unit: str = ""                     # canonical unit
    loinc: str | None = None
    flag: str | None = None            # H / L / C as printed by the lab
    status: ValueStatus = ValueStatus.ok

    @property
    def usable(self) -> bool:
        return self.value is not None and self.status in (ValueStatus.ok, ValueStatus.converted)


class Draw(BaseModel):
    draw_id: str
    collected: date
    lab_format: str = "unknown"
    fasting: bool | None = None
    values: list[LabValue] = Field(default_factory=list)
    needs_review: list[str] = Field(default_factory=list)  # extraction issues for a human

    def get(self, analyte: str) -> LabValue | None:
        for v in self.values:
            if v.analyte == analyte:
                return v
        return None


class WearableDay(BaseModel):
    """Daily summary metrics only. Raw sensor signals are out of scope by design."""
    day: date
    hrv_rmssd: float | None = None     # ms, nightly average
    resting_hr: float | None = None    # bpm
    sleep_hours: float | None = None
    steps: int | None = None


class Member(BaseModel):
    member_id: str
    first_name: str
    age: int
    sex: Literal["F", "M"]
    draws: list[Draw] = Field(default_factory=list)
    wearables: list[WearableDay] = Field(default_factory=list)
    visit_date: date

    def sorted_draws(self) -> list[Draw]:
        return sorted(self.draws, key=lambda d: d.collected)


# ---------- outputs ----------

class Evidence(BaseModel):
    analyte: str
    display: str
    values: list[tuple[str, float]]    # (iso date, value) oldest first
    unit: str
    note: str = ""


class PlanItem(BaseModel):
    item_id: str                       # stable: rule id
    rule_id: str
    category: Literal["discuss", "retest", "lifestyle", "refer", "monitor"]
    clinician_text: str
    member_text: str
    why: str                           # one line, human readable basis
    evidence: list[Evidence]
    source: str                        # protocol section and external reference
    priority: int = 2                  # 1 high, 3 low


class Flag(BaseModel):
    kind: Literal["critical", "conflict", "unit_change", "stale", "wearable_gap",
                  "implausible", "missing_unit", "unknown_analyte", "not_measured"]
    analyte: str | None = None
    message: str


class DraftPlan(BaseModel):
    member_id: str
    generated_for_visit: date
    status: Literal["draft", "blocked_critical"] = "draft"
    flags: list[Flag] = Field(default_factory=list)
    items: list[PlanItem] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)   # "what changed since last visit"
    disclaimer: str = ("Draft for clinician review. Not a diagnosis. Every item shows "
                       "its basis so it can be checked independently.")


class MemberSummary(BaseModel):
    member_id: str
    blocked: bool = False
    headline: str = ""
    body: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
