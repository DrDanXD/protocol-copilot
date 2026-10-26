"""Synthetic data: members, lab draws, wearable summaries, and lab PDFs.

Everything here is invented. PDFs use two generic layouts ("Layout A" table and
"Layout B" line list) that mimic how commercial lab reports are organised
without copying any real company's branding. Every page is watermarked
SYNTHETIC so nothing produced here can pass as a real record.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .catalog import CATALOG
from .schema import WearableDay

FIRST_NAMES = ["Sophia", "Marcus", "Elena", "James", "Priya", "Daniel", "Aisha", "Thomas",
               "Hannah", "Rafael", "Grace", "Oliver", "Mei", "Samuel", "Clara", "Victor"]


@dataclass
class Row:
    name: str          # name as printed
    value: str         # as printed, may be "<0.2" or "12,4"
    unit: str
    ref: str = ""
    flag: str = ""


def ref_string(analyte_id: str) -> str:
    a = CATALOG[analyte_id]
    if a.ref_low is not None and a.ref_high is not None:
        return f"{a.ref_low:g}-{a.ref_high:g}"
    if a.ref_high is not None:
        return f"<{a.ref_high:g}"
    if a.ref_low is not None:
        return f">{a.ref_low:g}"
    return ""


def flag_for(analyte_id: str, value: float) -> str:
    a = CATALOG[analyte_id]
    if a.critical_low is not None and value < a.critical_low:
        return "CL"
    if a.critical_high is not None and value > a.critical_high:
        return "CH"
    if a.ref_low is not None and value < a.ref_low:
        return "L"
    if a.ref_high is not None and value > a.ref_high:
        return "H"
    return ""


def row(analyte_id: str, value: float, unit: str | None = None, name: str | None = None,
        decimals: int | None = None) -> Row:
    a = CATALOG[analyte_id]
    unit = a.unit if unit is None else unit
    if decimals is None:
        decimals = 1 if abs(value) < 100 else 0
        if a.id in ("potassium", "creatinine", "hscrp", "tsh"):
            decimals = 2 if abs(value) < 10 else 1
    v = f"{value:.{decimals}f}"
    flag = flag_for(analyte_id, value) if unit == a.unit else ""
    return Row(name or a.display, v, unit, ref_string(analyte_id) if unit == a.unit else "", flag)


# ---------------- PDF rendering ----------------

def _watermark(c: canvas.Canvas) -> None:
    c.saveState()
    c.setFont("Helvetica-Bold", 60)
    c.setFillGray(0.92)
    c.translate(306, 396)
    c.rotate(35)
    c.drawCentredString(0, 0, "SYNTHETIC")
    c.restoreState()


def render_lab_pdf(path: Path, layout: str, member_label: str, member_id: str,
                   collected: date, fasting: bool | None, rows: list[Row]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle("Synthetic lab report")
    _watermark(c)
    y = 750
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, "SAMPLE REFERENCE LABORATORY  (SYNTHETIC DATA, NOT A REAL REPORT)")
    y -= 22
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Patient: {member_label}")
    c.drawString(320, y, f"Specimen ID: {member_id}-{collected:%Y%m%d}")
    y -= 14
    if layout == "A":
        c.drawString(50, y, f"Date Collected: {collected:%m/%d/%Y}")
    else:
        c.drawString(50, y, f"Collection Date: {collected:%Y-%m-%d}")
    if fasting is not None:
        c.drawString(320, y, f"Fasting: {'Yes' if fasting else 'No'}")
    y -= 26

    if layout == "A":
        c.setFont("Helvetica-Bold", 10)
        for x, h in ((50, "Test"), (250, "Result"), (320, "Flag"), (360, "Units"), (450, "Reference Interval")):
            c.drawString(x, y, h)
        y -= 6
        c.line(50, y, 560, y)
        y -= 14
        c.setFont("Helvetica", 10)
        for r in rows:
            if y < 70:
                c.showPage(); _watermark(c); y = 750; c.setFont("Helvetica", 10)
            c.drawString(50, y, r.name)
            c.drawString(250, y, r.value)
            c.drawString(320, y, r.flag)
            c.drawString(360, y, r.unit)
            c.drawString(450, y, r.ref)
            y -= 16
    else:  # layout B: one line per result
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "RESULTS")
        y -= 18
        c.setFont("Helvetica", 10)
        for r in rows:
            if y < 70:
                c.showPage(); _watermark(c); y = 750; c.setFont("Helvetica", 10)
            ref = f" (Ref: {r.ref})" if r.ref else ""
            flag = f" [{r.flag}]" if r.flag else ""
            c.drawString(50, y, f"{r.name.upper()}: {r.value} {r.unit}{ref}{flag}".replace("  ", " "))
            y -= 16
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 40, "Generated for software testing. Contains no real patient information.")
    c.save()
    return path


# ---------------- wearables ----------------

def wearable_series(start: date, days: int, rng: random.Random, hrv_base: float = 55,
                    hrv_drift: float = 0.0, rhr_base: float = 58, rhr_drift: float = 0.0,
                    gap: tuple[int, int] | None = None) -> list[WearableDay]:
    """Daily summaries. drift is total change across the window."""
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        if gap and gap[0] <= i < gap[1]:
            out.append(WearableDay(day=d))
            continue
        frac = i / max(days - 1, 1)
        out.append(WearableDay(
            day=d,
            hrv_rmssd=round(hrv_base + hrv_drift * frac + rng.gauss(0, 4), 1),
            resting_hr=round(rhr_base + rhr_drift * frac + rng.gauss(0, 1.5), 1),
            sleep_hours=round(min(9.5, max(4.5, rng.gauss(7.1, 0.6))), 2),
            steps=max(1500, int(rng.gauss(8200, 2200))),
        ))
    return out


# ---------------- demo cohort ----------------

BASE_PANEL = {
    "apob": 85, "ldl": 110, "hdl": 55, "tg": 110, "lpa": 30, "a1c": 5.3, "glucose": 88,
    "insulin": 6.0, "hscrp": 0.8, "vitd": 38, "ferritin": 120, "tsh": 1.8, "potassium": 4.3,
    "sodium": 140, "creatinine": 0.95, "egfr": 95, "alt": 24, "hgb": 14.2,
}


def jitter(panel: dict[str, float], rng: random.Random, pct: float = 0.06) -> dict[str, float]:
    """Random variation, capped per analyte so tightly regulated values stay realistic."""
    return {k: v * (1 + rng.uniform(-1, 1) * min(pct, CATALOG[k].tolerance / 2)) for k, v in panel.items()}


def demo_cohort(out_dir: Path, n: int = 12, seed: int = 7) -> list[dict]:
    """Writes PDFs plus a manifest describing each member. Returns the manifest."""
    rng = random.Random(seed)
    manifest = []
    visit = date(2026, 11, 2)
    for i in range(n):
        mid = f"M{1001 + i}"
        name = FIRST_NAMES[i % len(FIRST_NAMES)]
        sex = "F" if i % 2 == 0 else "M"
        base = jitter(BASE_PANEL, rng, 0.15)
        # give some members a story
        story = ["steady", "lipids_rising", "glucose_drift", "recovery_dropping", "vitd_low",
                 "improving"][i % 6]
        if i == 6:
            story = "critical_potassium"   # shows the guardrail in the demo
        draws = []
        for k, offset in enumerate((-240, -120, -10)):
            panel = jitter(base, rng, 0.04)
            step = k / 2
            if story == "lipids_rising":
                panel["apob"] = base["apob"] * (1 + 0.45 * step) + 10
                panel["ldl"] = base["ldl"] * (1 + 0.2 * step) + 10
            if story == "glucose_drift":
                panel["a1c"] = 5.4 + 0.25 * k
                panel["glucose"] = 92 + 5 * k
                panel["insulin"] = 8 + 3 * k
            if story == "vitd_low":
                panel["vitd"] = 24 - 2 * k
            if story == "critical_potassium" and k == 2:
                panel["potassium"] = 6.3
            if story == "improving":
                panel["apob"] = 118 - 14 * k
                panel["hscrp"] = 2.6 - 0.8 * k
            day = visit + timedelta(days=offset)
            layout = "A" if (i + k) % 2 == 0 else "B"
            rows = [row(a, v) for a, v in panel.items()]
            pdf = out_dir / mid / f"{mid}_{day:%Y%m%d}.pdf"
            render_lab_pdf(pdf, layout, f"{name} (synthetic)", mid, day, True, rows)
            draws.append({"pdf": str(pdf.relative_to(out_dir)), "collected": day.isoformat(),
                          "layout": layout})
        wear = wearable_series(visit - timedelta(days=90), 90, rng,
                               hrv_drift=-22 if story == "recovery_dropping" else 0,
                               rhr_drift=7 if story == "recovery_dropping" else 0)
        manifest.append({
            "member_id": mid, "first_name": name, "age": 38 + (i * 3) % 25, "sex": sex,
            "visit_date": visit.isoformat(), "story": story, "draws": draws,
            "wearables": [w.model_dump(mode="json") for w in wear],
        })
    return manifest
