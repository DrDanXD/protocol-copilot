"""Summarise a timed prep study. See docs/TIMED_STUDY.md."""
import csv
import sys
from statistics import median


def main(path: str) -> None:
    rows = list(csv.DictReader(open(path)))
    if not rows:
        sys.exit("No rows yet. Run the study first.")
    arms = {}
    for r in rows:
        arms.setdefault(r["arm"], []).append(r)
    for arm in ("manual", "copilot"):
        if arm not in arms:
            sys.exit(f"Missing arm: {arm}")
    out = {}
    for arm, rs in arms.items():
        out[arm] = median(float(r["minutes"]) for r in rs)
        print(f"{arm:8s} median {out[arm]:.1f} min/member  n={len(rs)}  "
              f"errors={sum(int(r['errors']) for r in rs)}")
    people = {r["participant"] for r in rows}
    roles = sorted({r["role"] for r in rows})
    saved = out["manual"] - out["copilot"]
    print(f"\nSaved {saved:.1f} min per member ({saved / out['manual']:.0%}). "
          f"{len(people)} participants ({', '.join(roles)}), {len({r['member_id'] for r in rows})} members.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/timed_study.csv")
