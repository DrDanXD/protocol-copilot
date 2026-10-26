"""Generate the synthetic cohort and print one member's draft plan.

    python scripts/demo.py            # builds data/demo, prints M1002
    python scripts/demo.py M1004
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from copilot.ingest import member_from_manifest  # noqa: E402
from copilot.member import member_summary  # noqa: E402
from copilot.plan import build_draft  # noqa: E402
from copilot.synth import demo_cohort  # noqa: E402

out = Path(__file__).resolve().parent.parent / "data" / "demo"
if not (out / "manifest.json").exists():
    (out / "manifest.json").write_text(json.dumps(demo_cohort(out), indent=1))
manifest = {e["member_id"]: e for e in json.loads((out / "manifest.json").read_text())}
mid = sys.argv[1] if len(sys.argv) > 1 else "M1002"
m = member_from_manifest(manifest[mid], out)
plan = build_draft(m)
print(f"{m.first_name} ({mid})  visit {m.visit_date}  status: {plan.status}\n")
print("What changed")
for c in plan.changes or ["Nothing moved more than 10%"]:
    print("  ", c)
if plan.flags:
    print("\nFlags")
    for f in plan.flags:
        print(f"   [{f.kind}] {f.message}")
print("\nDraft plan")
for i in plan.items:
    print(f"   {i.item_id:10s} {i.clinician_text}\n{'':14s}why: {i.why}\n{'':14s}source: {i.source}")
s = member_summary(plan, first_name=m.first_name)
print("\nMember preview" + (" (held)" if s.blocked else ""))
print("  ", s.headline)
for b in s.body:
    print("  ", b)
for n in s.next_steps:
    print("   ->", n)
