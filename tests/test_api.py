import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from copilot import api
from copilot.synth import demo_cohort


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("demo")
    (d / "manifest.json").write_text(json.dumps(demo_cohort(d, n=6)))
    api.DATA, api.EDIT_LOG = d, d / "edits.jsonl"
    api._cohort.cache_clear()
    return TestClient(api.app)


def test_draft_and_approve_roundtrip(client):
    assert len(client.get("/members").json()) == 6
    d = client.get("/members/M1002/draft").json()
    items = d["plan"]["items"]
    assert items and all(i["why"] and i["source"] for i in items)
    body = [{"item_id": i["item_id"], "clinician_text": i["clinician_text"]} for i in items]
    r = client.post("/members/M1002/approve?clinician=dr_a", json=body).json()
    assert set(r["edit_record"]["outcomes"].values()) == {"kept"}
    assert not r["member_summary"]["blocked"]
    learn = client.get("/learning").json()
    assert learn["approvals"] == 1 and learn["acceptance_rate"] == 1.0


def test_extract_endpoint(client):
    pdf = next(Path(api.DATA).rglob("*.pdf"))
    r = client.post("/extract", files={"file": ("r.pdf", pdf.read_bytes(), "application/pdf")}).json()
    assert len(r["values"]) == 18
