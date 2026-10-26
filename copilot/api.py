"""HTTP API for the clinician console.

    uvicorn copilot.api:app --reload

Endpoints
  POST /extract                 upload a lab PDF, get structured values + review notes
  GET  /members                 demo cohort list
  GET  /members/{id}/draft      draft plan with flags, changes, evidence, sources
  POST /members/{id}/approve    clinician-approved items -> edit log + member summary
  GET  /learning                per-rule edit stats and acceptance rate
  GET  /snapshot                everything the console needs in one call
  GET  /                        the clinician console
"""
from __future__ import annotations

import json
import tempfile
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .edits import ApprovedItem, acceptance_rate, compare, log, read_log, rule_stats
from .extract import extract_pdf
from .ingest import member_from_manifest
from .member import member_summary
from .plan import build_draft
from .schema import PlanItem
from .snapshot import build_snapshot

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "demo"
EDIT_LOG = ROOT / "data" / "edit_log.jsonl"

app = FastAPI(title="Protocol Copilot", version="0.1.0",
              description="Drafts only. Every suggestion shows its basis. Clinician approves.")


@lru_cache
def _cohort() -> dict:
    manifest = json.loads((DATA / "manifest.json").read_text())
    return {e["member_id"]: member_from_manifest(e, DATA) for e in manifest}


def _member(mid: str):
    m = _cohort().get(mid)
    if m is None:
        raise HTTPException(404, "member not found")
    return m


CONSOLE = ROOT / "console" / "index.html"


@app.get("/", include_in_schema=False)
def console():
    return FileResponse(CONSOLE)


@app.get("/snapshot")
def snapshot():
    return build_snapshot(list(_cohort().values()))


@app.post("/extract")
async def extract(file: UploadFile):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp.flush()
        return extract_pdf(tmp.name).model_dump(mode="json")


@app.get("/members")
def members():
    out = []
    for m in _cohort().values():
        d = build_draft(m)
        out.append({"member_id": m.member_id, "first_name": m.first_name, "status": d.status,
                    "items": len(d.items), "flags": [f.kind for f in d.flags]})
    return out


@app.get("/members/{mid}/draft")
def draft(mid: str):
    m = _member(mid)
    d = build_draft(m)
    return {"plan": d.model_dump(mode="json"),
            "member_preview": member_summary(d, first_name=m.first_name).model_dump()}


@app.post("/members/{mid}/approve")
def approve(mid: str, items: list[ApprovedItem], clinician: str = "unknown",
            critical_contact_logged: bool = False):
    """A critical draft stays blocked until the clinician confirms the member was contacted."""
    m = _member(mid)
    d = build_draft(m)
    rec = compare(d, items, clinician)
    log(rec, EDIT_LOG)
    drafted = {i.item_id: i for i in d.items}
    approved = []
    for a in items:
        base = drafted.get(a.item_id)
        approved.append(PlanItem(
            item_id=a.item_id, rule_id=base.rule_id if base else "CLINICIAN",
            category=base.category if base else "discuss", priority=base.priority if base else 2,
            clinician_text=a.clinician_text, member_text=a.member_text or (base.member_text if base else ""),
            why=base.why if base else "Added by clinician", evidence=base.evidence if base else [],
            source=base.source if base else "Clinician judgement"))
    return {"edit_record": rec.model_dump(),
            "member_summary": member_summary(d, approved, m.first_name,
                                             contacted=critical_contact_logged).model_dump()}


@app.get("/learning")
def learning():
    recs = read_log(EDIT_LOG)
    return {"approvals": len(recs), "acceptance_rate": acceptance_rate(recs), "rules": rule_stats(recs)}
