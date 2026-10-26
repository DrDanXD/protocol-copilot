"""Build a Member from PDFs on disk plus wearable summaries."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .extract import extract_pdf
from .schema import Member, WearableDay


def member_from_manifest(entry: dict, base_dir: str | Path) -> Member:
    base = Path(base_dir)
    draws = [extract_pdf(base / d["pdf"]) for d in entry["draws"]]
    return Member(
        member_id=entry["member_id"], first_name=entry["first_name"], age=entry["age"],
        sex=entry["sex"], visit_date=date.fromisoformat(entry["visit_date"]), draws=draws,
        wearables=[WearableDay(**w) for w in entry.get("wearables", [])],
    )
