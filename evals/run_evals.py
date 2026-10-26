"""Score the test set and publish the pass rate.

    python -m evals.run_evals            # prints a table, writes evals/RESULTS.md

Every case also gets three checks that apply to everything:
  - every plan item shows its basis (why) and its source
  - member text never uses banned words
  - never more than 3 next steps for a member
"""
from __future__ import annotations

import json
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

from copilot.extract import extract_pdf
from copilot.member import banned_terms, member_summary
from copilot.plan import build_draft
from copilot.synth import BASE_PANEL, Row, render_lab_pdf, row

from .cases import CASES, Case

ROOT = Path(__file__).resolve().parent


def score_case(c: Case) -> list[str]:
    errs: list[str] = []
    m = c.member()
    plan = build_draft(m)
    s = member_summary(plan, first_name=m.first_name)
    fired = {i.item_id for i in plan.items}
    kinds = {f.kind for f in plan.flags}
    for r in c.fires - fired:
        errs.append(f"expected {r} to fire")
    for r in c.not_fires & fired:
        errs.append(f"{r} fired but should not")
    for k in c.flags - kinds:
        errs.append(f"missing flag {k}")
    for k in c.no_flags & kinds:
        errs.append(f"unexpected flag {k}")
    if plan.status != c.status:
        errs.append(f"status {plan.status}, expected {c.status}")
    if c.member_blocked is not None and s.blocked != c.member_blocked:
        errs.append(f"member summary blocked={s.blocked}, expected {c.member_blocked}")
    for i in plan.items:
        if not i.why or not i.source:
            errs.append(f"{i.item_id} has no visible basis")
    if not s.blocked:
        bad = banned_terms(" ".join([s.headline, *s.body, *s.next_steps]))
        if bad:
            errs.append(f"banned words in member text: {bad}")
        if len(s.next_steps) > 3:
            errs.append("more than 3 next steps")
    if c.check:
        e = c.check(m, plan, s)
        if e:
            errs.append(e)
    return errs


# ---------------- extraction round trips ----------------

def _roundtrip(layout: str, rows: list[Row], collected: date | None = date(2026, 10, 20)):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "r.pdf"
        render_lab_pdf(p, layout, "Test (synthetic)", "X1", collected or date(2026, 1, 1), True, rows)
        if collected is None:   # strip the date line to simulate a report without one
            from reportlab.pdfgen import canvas  # noqa: F401  (render once more without date)
            _render_without_date(p, layout, rows)
        return extract_pdf(p)


def _render_without_date(p: Path, layout: str, rows: list[Row]) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(p), pagesize=letter)
    y = 700
    c.setFont("Helvetica", 10)
    c.drawString(50, y, "Patient: Test (synthetic)")
    y -= 30
    c.drawString(50, y, "Test Result Flag Units Reference Interval" if layout == "A" else "RESULTS")
    y -= 16
    for r in rows:
        line = (f"{r.name} {r.value} {r.unit} {r.ref}" if layout == "A"
                else f"{r.name.upper()}: {r.value} {r.unit}")
        c.drawString(50, y, line)
        y -= 16
    c.save()


def extraction_cases() -> list[tuple[str, str, str, callable]]:
    full = [row(a, v) for a, v in BASE_PANEL.items()]

    def exact(layout):
        def f():
            d = _roundtrip(layout, full)
            got = {v.analyte: v.value for v in d.values}
            wrong = [a for a, v in BASE_PANEL.items() if got.get(a) is None or abs(got[a] - float(row(a, v).value)) > 1e-9]
            return [f"value mismatch: {wrong}"] if wrong else []
        return f

    def commas():
        d = _roundtrip("B", [Row("Hemoglobin A1c", "5,4", "%"), Row("Ferritin", "1,200", "ng/mL")])
        got = {v.analyte: v.value for v in d.values}
        errs = []
        if got.get("a1c") != 5.4: errs.append(f"a1c read as {got.get('a1c')}")
        if got.get("ferritin") != 1200: errs.append(f"ferritin read as {got.get('ferritin')}")
        return errs

    def censored():
        d = _roundtrip("A", [Row("hs-CRP", "<0.2", "mg/L", "<1")])
        v = d.get("hscrp")
        errs = [] if v and v.value == 0.2 else ["censored value not read"]
        if not any("limit of detection" in n for n in d.needs_review):
            errs.append("censored value not surfaced for review")
        return errs

    def no_date():
        d = _roundtrip("A", full[:3], collected=None)
        return [] if any("Collection date not found" in n for n in d.needs_review) else ["missing date not flagged"]

    def dup():
        d = _roundtrip("A", [row("apob", 95), row("apob", 140)])
        errs = [] if any("reported twice" in n for n in d.needs_review) else ["duplicate not flagged"]
        if d.get("apob") and d.get("apob").value != 95:
            errs.append("duplicate overwrote first value")
        return errs

    def watermark():
        d = _roundtrip("A", full)
        junk = [v.raw_unit for v in d.values if any(ch in v.raw_unit for ch in "SYNTHEC")]
        return [f"watermark leaked into units: {junk}"] if junk else []

    return [
        ("E01", "extraction", "Layout A: 18 values read back exactly", exact("A")),
        ("E02", "extraction", "Layout B: 18 values read back exactly", exact("B")),
        ("E03", "extraction", "Decimal comma and thousands comma", commas),
        ("E04", "extraction", "'<0.2' read as 0.2 and flagged for review", censored),
        ("E05", "extraction", "Report with no collection date is flagged", no_date),
        ("E06", "extraction", "Same test twice in one report keeps the first and flags it", dup),
        ("E07", "extraction", "Diagonal watermark never leaks into values", watermark),
    ]


def run() -> dict:
    results = []
    for c in CASES:
        try:
            errs = score_case(c)
        except Exception as e:  # a crash is a failure, not a skip
            errs = [f"crashed: {type(e).__name__}: {e}"]
        results.append({"id": c.id, "group": c.group, "title": c.title, "pass": not errs, "errors": errs})
    for cid, group, title, fn in extraction_cases():
        try:
            errs = fn()
        except Exception as e:
            errs = [f"crashed: {type(e).__name__}: {e}"]
        results.append({"id": cid, "group": group, "title": title, "pass": not errs, "errors": errs})
    passed = sum(r["pass"] for r in results)
    return {"total": len(results), "passed": passed, "pass_rate": round(passed / len(results), 4),
            "results": results}


def write_report(out: dict) -> None:
    by_group = Counter(r["group"] for r in out["results"])
    ok_group = Counter(r["group"] for r in out["results"] if r["pass"])
    lines = ["# Test set results", "",
             f"**{out['passed']} of {out['total']} cases pass ({out['pass_rate']:.0%}).**", "",
             "Generated by `python -m evals.run_evals`. Failures are listed, not hidden.", "",
             "| Group | Pass |", "|---|---|"]
    lines += [f"| {g} | {ok_group[g]}/{n} |" for g, n in by_group.items()]
    lines += ["", "| Case | What it checks | Result |", "|---|---|---|"]
    for r in out["results"]:
        res = "pass" if r["pass"] else "FAIL: " + "; ".join(r["errors"])
        lines.append(f"| {r['id']} | {r['title']} | {res} |")
    (ROOT / "RESULTS.md").write_text("\n".join(lines) + "\n")
    (ROOT / "results.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    out = run()
    write_report(out)
    for r in out["results"]:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['id']}  {r['title']}"
              + ("" if r["pass"] else f"\n      {r['errors']}"))
    print(f"\n{out['passed']}/{out['total']} passed ({out['pass_rate']:.1%})")
    sys.exit(0 if out["passed"] == out["total"] else 1)
