"""Draft plan assembly and hard guardrails.

Order of operations matters:
1. Trends are computed (pure arithmetic).
2. Critical values are checked FIRST, with fixed thresholds and no model.
   A critical value blocks the member-facing summary until a clinician acts.
3. Protocol rules fire. Each item carries its rule id, evidence and source.
4. Paused markers (conflicting draws) get a retest item instead of a rule.

The output is a DRAFT. Nothing is sent to a member from here.
"""
from __future__ import annotations

from .catalog import CATALOG
from .rules import WEARABLE_LABELS, Protocol, analytes_in, evaluate, fill, load_protocol, metrics_in
from .schema import DraftPlan, Evidence, Flag, Member, PlanItem
from .trends import TrendReport, analyse, what_changed


def critical_flags(rep: TrendReport) -> list[Flag]:
    flags = []
    for aid, x in rep.latest_values.items():
        a = CATALOG.get(aid)
        if a is None:
            continue
        if a.critical_low is not None and x < a.critical_low:
            flags.append(Flag(kind="critical", analyte=aid,
                              message=f"{a.display} {x:g} {a.unit} is below the critical limit "
                                      f"{a.critical_low:g}. Contact the member today per clinic policy"))
        if a.critical_high is not None and x > a.critical_high:
            flags.append(Flag(kind="critical", analyte=aid,
                              message=f"{a.display} {x:g} {a.unit} is above the critical limit "
                                      f"{a.critical_high:g}. Contact the member today per clinic policy"))
    return flags


def _evidence(rep: TrendReport, analytes: set[str], metrics: set[str]) -> list[Evidence]:
    ev = []
    for aid in sorted(analytes):
        t = rep.analytes.get(aid)
        if not t:
            continue
        a = CATALOG[aid]
        ev.append(Evidence(analyte=aid, display=a.display, unit=a.unit,
                           values=[(d.isoformat(), v) for d, v in t.series[-4:]],
                           note="non-comparable unit in an earlier draw" if t.unit_changed else ""))
    for m in sorted(metrics):
        w = rep.wearables.get(m)
        if not w or w.recent is None:
            continue
        ev.append(Evidence(analyte=m, display=WEARABLE_LABELS[m], unit="",
                           values=[("baseline", w.baseline or 0.0), ("last 14 days", w.recent)],
                           note="daily summary average"))
    return ev


def _why(ev: list[Evidence]) -> str:
    parts = []
    for e in ev:
        vals = " → ".join(f"{v:g}" for _, v in e.values[-3:])
        parts.append(f"{e.display} {vals} {e.unit}".strip())
    return " · ".join(parts)


def build_draft(member: Member, protocol: Protocol | None = None) -> DraftPlan:
    protocol = protocol or load_protocol()
    rep = analyse(member)
    plan = DraftPlan(member_id=member.member_id, generated_for_visit=member.visit_date)
    plan.flags.extend(rep.flags)
    plan.changes = what_changed(rep)

    crit = critical_flags(rep)
    if crit:
        plan.status = "blocked_critical"
        plan.flags = crit + plan.flags
        for f in crit:
            a = CATALOG[f.analyte]
            plan.items.append(PlanItem(
                item_id=f"CRIT-{f.analyte}", rule_id="CRITICAL", category="refer", priority=1,
                clinician_text=f.message, member_text="",
                why=f"{a.display} {rep.latest_values[f.analyte]:g} {a.unit} on {rep.latest_draw_date}",
                evidence=_evidence(rep, {f.analyte}, set()),
                source="Clinic critical value policy (fixed thresholds, no model involved)"))

    for rule in protocol.rules:
        if not evaluate(rule.when, rep):
            continue
        ev = _evidence(rep, analytes_in(rule.when), metrics_in(rule.when))
        plan.items.append(PlanItem(
            item_id=rule.id, rule_id=rule.id, category=rule.category, priority=rule.priority,
            clinician_text=fill(rule.clinician, rep), member_text=fill(rule.member, rep),
            why=_why(ev), evidence=ev, source=f"{protocol.clinic} protocol {protocol.version} · "
                                             f"{rule.id} · {rule.source}"))

    for f in rep.flags:
        if f.kind == "conflict" and f.analyte:
            a = CATALOG[f.analyte]
            plan.items.append(PlanItem(
                item_id=f"RETEST-{f.analyte}", rule_id="CONFLICT", category="retest", priority=1,
                clinician_text=f"Draws disagree for {a.display}. Retest before acting on this marker.",
                member_text="We will repeat one test to make sure the result is accurate.",
                why=f.message, evidence=_evidence(rep, {f.analyte}, set()),
                source="Copilot data quality check: draws within 14 days differ by more than "
                       "twice the assay tolerance"))

    plan.items.sort(key=lambda i: (i.priority, i.item_id))
    return plan
