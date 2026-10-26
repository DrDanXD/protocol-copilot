"""Freeze the demo cohort into console/snapshot.json so the console runs without a server.

    python scripts/export_snapshot.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from copilot.ingest import member_from_manifest  # noqa: E402
from copilot.snapshot import build_snapshot  # noqa: E402
from copilot.synth import demo_cohort  # noqa: E402

data = ROOT / "data" / "demo"
if not (data / "manifest.json").exists():
    (data / "manifest.json").write_text(json.dumps(demo_cohort(data), indent=1))
members = [member_from_manifest(e, data) for e in json.loads((data / "manifest.json").read_text())]
snap = build_snapshot(members)
(ROOT / "console" / "snapshot.json").write_text(json.dumps(snap))
print(f"wrote {len(snap['members'])} members")
