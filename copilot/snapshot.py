"""One payload with everything the console needs: members, drafts, labs, ranges."""
from __future__ import annotations

from .catalog import CATALOG
from .member import member_summary
from .plan import build_draft
from .rules import load_protocol
from .schema import Member


def build_snapshot(members: list[Member]) -> dict:
    out = {"protocol": load_protocol().version, "members": [],
           "catalog": {a.id: {"display": a.display, "unit": a.unit, "ref_low": a.ref_low,
                              "ref_high": a.ref_high, "critical_low": a.critical_low,
                              "critical_high": a.critical_high} for a in CATALOG.values()}}
    for m in members:
        d = build_draft(m)
        draws = m.sorted_draws()
        out["members"].append({
            "member_id": m.member_id, "first_name": m.first_name, "age": m.age,
            "last_draw": draws[-1].collected.isoformat() if draws else None,
            "fasting": draws[-1].fasting if draws else None,
            "plan": d.model_dump(mode="json"),
            "member_preview": member_summary(d, first_name=m.first_name).model_dump(),
            "labs": [{"draw": dr.collected.isoformat(), "review": dr.needs_review, "values": [
                {"analyte": v.analyte, "name": v.raw_name, "raw": f"{v.raw_value} {v.raw_unit}".strip(),
                 "value": v.value, "unit": v.unit, "status": v.status.value, "loinc": v.loinc}
                for v in dr.values]} for dr in draws],
        })
    return out
