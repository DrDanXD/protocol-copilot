"""Learning from clinician edits.

Every approval is compared with the draft and stored as a small diff record.
Per-rule stats show which protocol rules clinicians keep rewriting, so the
clinic can fix the protocol itself. No model is fine-tuned on member data.
"""
from __future__ import annotations

import difflib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from .schema import DraftPlan

REVIEW_MIN_SHOWN = 5
REVIEW_EDIT_RATE = 0.5


class ApprovedItem(BaseModel):
    item_id: str
    clinician_text: str
    member_text: str = ""


class EditRecord(BaseModel):
    member_id: str
    at: str
    clinician: str
    outcomes: dict[str, str]     # item_id -> kept | reworded | removed | added
    similarity: dict[str, float]  # item_id -> 0..1 text similarity for reworded items
    added_text: dict[str, str]


def compare(draft: DraftPlan, approved: list[ApprovedItem], clinician: str = "unknown") -> EditRecord:
    drafted = {i.item_id: i for i in draft.items}
    final = {a.item_id: a for a in approved}
    outcomes, sim, added = {}, {}, {}
    for iid, item in drafted.items():
        if iid not in final:
            outcomes[iid] = "removed"
            continue
        a = final[iid]
        same = (a.clinician_text.strip() == item.clinician_text.strip()
                and (not a.member_text or a.member_text.strip() == item.member_text.strip()))
        if same:
            outcomes[iid] = "kept"
        else:
            outcomes[iid] = "reworded"
            sim[iid] = round(difflib.SequenceMatcher(None, item.clinician_text, a.clinician_text).ratio(), 3)
    for iid, a in final.items():
        if iid not in drafted:
            outcomes[iid] = "added"
            added[iid] = a.clinician_text
    return EditRecord(member_id=draft.member_id, clinician=clinician,
                      at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      outcomes=outcomes, similarity=sim, added_text=added)


def log(record: EditRecord, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(record.model_dump_json() + "\n")


def read_log(path: str | Path) -> list[EditRecord]:
    p = Path(path)
    if not p.exists():
        return []
    return [EditRecord(**json.loads(ln)) for ln in p.read_text().splitlines() if ln.strip()]


def rule_of(item_id: str) -> str:
    for prefix in ("CRIT-", "RETEST-"):
        if item_id.startswith(prefix):
            return prefix.rstrip("-")
    return item_id


def rule_stats(records: list[EditRecord]) -> list[dict]:
    """Per rule: how often shown, kept, reworded, removed, and whether to review it."""
    s: dict[str, dict] = defaultdict(lambda: {"shown": 0, "kept": 0, "reworded": 0, "removed": 0, "added": 0})
    for r in records:
        for iid, outcome in r.outcomes.items():
            row = s[rule_of(iid)]
            if outcome != "added":
                row["shown"] += 1
            row[outcome] += 1
    out = []
    for rid, row in sorted(s.items()):
        shown = row["shown"]
        edit_rate = (row["reworded"] + row["removed"]) / shown if shown else 0.0
        out.append({"rule": rid, **row, "edit_rate": round(edit_rate, 2),
                    "review_protocol": shown >= REVIEW_MIN_SHOWN and edit_rate >= REVIEW_EDIT_RATE})
    return out


def acceptance_rate(records: list[EditRecord]) -> float | None:
    """Share of drafted items approved without changes. The 'drafts get closer' number."""
    shown = kept = 0
    for r in records:
        for o in r.outcomes.values():
            if o != "added":
                shown += 1
                kept += o == "kept"
    return round(kept / shown, 3) if shown else None
