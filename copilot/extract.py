"""Lab PDF -> structured, validated values.

Two extraction paths share one validator:

1. Deterministic parser for known layouts (default, no network, fully tested).
2. Optional LLM path for unfamiliar layouts. The model only proposes rows.
   The same validator then decides what is usable. Nothing the model returns
   is trusted until it passes unit and plausibility checks.

Anything the validator cannot accept is kept, marked unusable, and listed in
`needs_review` so a human sees it. Values are never silently guessed.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import pdfplumber

from .catalog import CATALOG, lookup, to_canonical
from .schema import Draw, LabValue, ValueStatus

NUM = r"[<>]?\d[\d,]*(?:\.\d+)?"
REF_RE = re.compile(r"^[<>]?\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?$")
ROW_A = re.compile(
    rf"^(?P<name>.+?)\s+(?P<val>{NUM})(?:\s+(?P<flag>CH|CL|HH|LL|H|L))?"
    rf"(?:\s+(?P<unit>\S+))?(?:\s+(?P<ref>\S+))?$")
ROW_B = re.compile(
    rf"^(?P<name>[^:]+):\s*(?P<val>{NUM})\s*(?P<unit>[^\s(\[]*)\s*"
    rf"(?:\(Ref:\s*(?P<ref>[^)]*)\))?\s*(?:\[(?P<flag>\w+)\])?$")


# ---------------- text ----------------

def pdf_text(path: str | Path) -> str:
    """Horizontal body text only, so rotated or oversized watermarks never leak into rows."""
    def keep(o: dict) -> bool:
        if o.get("object_type") != "char":
            return True
        m = o.get("matrix") or (1, 0, 0, 1)
        return abs(m[1]) < 1e-6 and abs(m[2]) < 1e-6 and o.get("size", 10) < 40

    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            clean = page.filter(keep)
            pages.append(clean.extract_text() or "")
    return "\n".join(pages)


def _parse_number(s: str) -> tuple[float, bool]:
    """Returns (value, censored). Handles '<0.2', '1,200' and '12,4'."""
    censored = s[0] in "<>"
    s = s.lstrip("<>")
    if "," in s:
        head, _, tail = s.rpartition(",")
        s = s.replace(",", "") if len(tail) == 3 and "." not in tail else f"{head.replace(',', '')}.{tail}"
    return float(s), censored


def _parse_date(text: str) -> date | None:
    m = re.search(r"Date Collected:\s*(\d{2}/\d{2}/\d{4})", text)
    if m:
        return datetime.strptime(m.group(1), "%m/%d/%Y").date()
    m = re.search(r"Collection Date:\s*(\d{4}-\d{2}-\d{2})", text)
    if m:
        return date.fromisoformat(m.group(1))
    return None


def detect_layout(text: str) -> str:
    if re.search(r"^Test\s+Result\s+Flag\s+Units", text, re.M):
        return "A"
    if re.search(r"^RESULTS\s*$", text, re.M):
        return "B"
    return "unknown"


def parse_rows(text: str, layout: str) -> list[dict]:
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if (layout == "A" and ln.startswith("Test ")) or (layout == "B" and ln.strip() == "RESULTS"):
            start = i + 1
            break
    if start is None:
        return []
    rows = []
    for ln in lines[start:]:
        ln = ln.strip()
        if not ln or ln.startswith("Generated for software testing"):
            continue
        m = (ROW_A if layout == "A" else ROW_B).match(ln)
        if not m:
            continue
        d = {k: (v or "").strip() for k, v in m.groupdict().items()}
        # Layout A with an empty unit cell: the ref range lands in the unit slot
        if layout == "A" and d["unit"] and REF_RE.match(d["unit"]) and not d["ref"]:
            d["ref"], d["unit"] = d["unit"], ""
        rows.append(d)
    return rows


# ---------------- validation (shared by both paths) ----------------

def validate_row(name: str, raw_value: str, raw_unit: str, flag: str = "") -> tuple[LabValue, list[str]]:
    issues: list[str] = []
    analyte = lookup(name)
    if analyte is None:
        return LabValue(analyte=name.lower(), raw_name=name, raw_value=raw_value, raw_unit=raw_unit,
                        flag=flag or None, status=ValueStatus.unknown_analyte), \
            [f"Unknown test '{name}': not mapped, left out of the plan"]
    try:
        num, censored = _parse_number(raw_value)
    except ValueError:
        return LabValue(analyte=analyte.id, raw_name=name, raw_value=raw_value, raw_unit=raw_unit,
                        loinc=analyte.loinc, status=ValueStatus.implausible), \
            [f"{analyte.display}: could not read value '{raw_value}'"]
    if censored:
        issues.append(f"{analyte.display}: reported as '{raw_value}' (limit of detection)")
    value, conv = to_canonical(analyte, num, raw_unit)
    lv = LabValue(analyte=analyte.id, raw_name=name, raw_value=raw_value, raw_unit=raw_unit,
                  unit=analyte.unit, loinc=analyte.loinc, flag=flag or None)
    if conv in ("missing_unit", "unknown_unit", "incompatible_unit"):
        lv.status = ValueStatus(conv)
        msg = {"missing_unit": "no unit printed",
               "unknown_unit": f"unit '{raw_unit}' not recognised",
               "incompatible_unit": f"unit '{raw_unit}' measures something different from "
                                    f"{analyte.unit} and cannot be converted"}[conv]
        issues.append(f"{analyte.display}: {msg}. Value held for review")
        return lv, issues
    lo, hi = analyte.plausible
    if not (lo <= value <= hi):
        lv.status = ValueStatus.implausible
        issues.append(f"{analyte.display}: {raw_value} {raw_unit} is outside the plausible range "
                      f"({lo:g}-{hi:g} {analyte.unit}). Likely a transcription error. Held for review")
        return lv, issues
    lv.value = value
    lv.status = ValueStatus.converted if conv == "converted" else ValueStatus.ok
    if conv == "converted":
        issues.append(f"{analyte.display}: converted {raw_value} {raw_unit} to {value:g} {analyte.unit}")
    return lv, issues


def build_draw(rows: list[dict], collected: date, draw_id: str, layout: str,
               fasting: bool | None) -> Draw:
    draw = Draw(draw_id=draw_id, collected=collected, lab_format=layout, fasting=fasting)
    seen: set[str] = set()
    for r in rows:
        lv, issues = validate_row(r["name"], r["val"], r.get("unit", ""), r.get("flag", ""))
        if lv.analyte in seen:
            draw.needs_review.append(f"{lv.raw_name}: reported twice in one draw, second value ignored")
            continue
        seen.add(lv.analyte)
        draw.values.append(lv)
        draw.needs_review.extend(i for i in issues if "converted" not in i)
    return draw


def extract_pdf(path: str | Path, use_llm: bool | None = None) -> Draw:
    text = pdf_text(path)
    layout = detect_layout(text)
    collected = _parse_date(text)
    fm = re.search(r"Fasting:\s*(Yes|No)", text)
    fasting = None if not fm else fm.group(1) == "Yes"
    sid = re.search(r"Specimen ID:\s*(\S+)", text)
    draw_id = sid.group(1) if sid else Path(path).stem

    if layout != "unknown":
        rows = parse_rows(text, layout)
    elif use_llm is not False and os.environ.get("ANTHROPIC_API_KEY"):
        rows, llm_date = llm_rows(text)
        collected = collected or llm_date
        layout = "llm"
    else:
        draw = Draw(draw_id=draw_id, collected=collected or date.min, lab_format="unknown")
        draw.needs_review.append("Unrecognised report layout and no LLM configured. Enter values manually")
        return draw

    if collected is None:
        draw = build_draw(rows, date.min, draw_id, layout, fasting)
        draw.needs_review.insert(0, "Collection date not found. Trends will skip this draw until it is set")
        return draw
    return build_draw(rows, collected, draw_id, layout, fasting)


# ---------------- optional LLM path ----------------

LLM_PROMPT = """You convert lab report text into JSON. Copy values exactly as printed.
Do not convert units, do not fix typos, do not infer missing values.
Return only JSON: {"collected": "YYYY-MM-DD" or null,
"rows": [{"name": str, "val": str, "unit": str, "flag": str}]}

Report text:
"""


def llm_rows(text: str) -> tuple[list[dict], date | None]:
    """Ask Claude to transcribe rows. Output still goes through validate_row."""
    import anthropic  # optional dependency

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=os.environ.get("COPILOT_MODEL", "claude-sonnet-5-5"),
        max_tokens=4000,
        messages=[{"role": "user", "content": LLM_PROMPT + text}],
    )
    raw = msg.content[0].text.strip()
    raw = raw[raw.find("{"): raw.rfind("}") + 1]
    data = json.loads(raw)
    collected = date.fromisoformat(data["collected"]) if data.get("collected") else None
    rows = [{"name": r.get("name", ""), "val": str(r.get("val", "")), "unit": r.get("unit", ""),
             "flag": r.get("flag", "")} for r in data.get("rows", [])]
    return rows, collected
