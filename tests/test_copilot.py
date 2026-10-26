import pytest

from copilot.edits import ApprovedItem, acceptance_rate, compare, rule_stats
from copilot.member import banned_terms
from copilot.plan import build_draft
from copilot.rules import load_protocol
from evals.cases import CASES, mk, panel
from evals.run_evals import extraction_cases, score_case


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_case(case):
    assert score_case(case) == []


@pytest.mark.parametrize("cid,group,title,fn", extraction_cases(), ids=[c[0] for c in extraction_cases()])
def test_extraction(cid, group, title, fn):
    assert fn() == []


def test_protocol_member_texts_are_calm():
    for r in load_protocol().rules:
        assert banned_terms(r.member) == [], r.id


def test_every_rule_names_a_source():
    for r in load_protocol().rules:
        assert len(r.source) > 10, r.id


def test_edit_learning_counts_outcomes():
    m = mk([(120, panel(apob=110), True), (5, panel(apob=140, a1c=6.0, vitd=15), True)])
    draft = build_draft(m)
    ids = [i.item_id for i in draft.items]
    assert {"LIPID-01", "GLY-01", "VITD-01"} <= set(ids)
    keep = [ApprovedItem(item_id=i.item_id, clinician_text=i.clinician_text, member_text=i.member_text)
            for i in draft.items if i.item_id != "VITD-01"]
    keep[0] = ApprovedItem(item_id=keep[0].item_id, clinician_text=keep[0].clinician_text + " Also order a CAC scan.")
    keep.append(ApprovedItem(item_id="CUSTOM-1", clinician_text="Refer to dietitian"))
    rec = compare(draft, keep, clinician="dr_a")
    assert rec.outcomes["VITD-01"] == "removed"
    assert rec.outcomes[keep[0].item_id] == "reworded"
    assert rec.outcomes["CUSTOM-1"] == "added"
    stats = {s["rule"]: s for s in rule_stats([rec] * 5)}
    assert stats["VITD-01"]["review_protocol"] is True     # removed 5 of 5 times
    untouched = next(i for i in ids if i not in ("VITD-01", keep[0].item_id))
    assert stats[keep[0].item_id]["review_protocol"] is True   # reworded 5 of 5 times
    assert stats[untouched]["review_protocol"] is False
    assert 0 < acceptance_rate([rec]) < 1
