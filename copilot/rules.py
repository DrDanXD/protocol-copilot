"""Protocol rules engine.

Code decides which recommendation fires. The rule file is the clinic's own
protocol, so every item in a draft points to a rule id, the values that
triggered it, and the guideline or clinic policy behind it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .catalog import CATALOG
from .trends import TrendReport

DEFAULT_PROTOCOL = Path(__file__).resolve().parent.parent / "protocols" / "clinic_protocol.yaml"
WEARABLE_LABELS = {"hrv_rmssd": "HRV (ms)", "resting_hr": "Resting HR (bpm)",
                   "sleep_hours": "Sleep (h)", "steps": "Steps"}


@dataclass
class Rule:
    id: str
    title: str
    category: str
    priority: int
    when: dict
    clinician: str
    member: str
    source: str


@dataclass
class Protocol:
    version: str
    clinic: str
    rules: list[Rule]


def load_protocol(path: str | Path = DEFAULT_PROTOCOL) -> Protocol:
    data = yaml.safe_load(Path(path).read_text())
    rules = [Rule(**r) for r in data["rules"]]
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate rule ids in protocol")
    for r in rules:
        _check_condition(r.when, r.id)
    return Protocol(data["version"], data["clinic"], rules)


_KEYS = {"latest", "rising", "falling", "wearable", "wearable_level", "fasting", "all", "any", "not"}


def _check_condition(c: dict, rid: str) -> None:
    if len(c) != 1 or next(iter(c)) not in _KEYS:
        raise ValueError(f"{rid}: bad condition {c}")
    k, v = next(iter(c.items()))
    if k in ("all", "any"):
        for sub in v:
            _check_condition(sub, rid)
    elif k == "not":
        _check_condition(v, rid)
    elif k in ("latest", "rising", "falling") and v["analyte"] not in CATALOG:
        raise ValueError(f"{rid}: unknown analyte {v['analyte']}")


def analytes_in(c: dict) -> set[str]:
    k, v = next(iter(c.items()))
    if k in ("all", "any"):
        return set().union(*(analytes_in(s) for s in v))
    if k == "not":
        return analytes_in(v)
    if k in ("latest", "rising", "falling"):
        return {v["analyte"]}
    return set()


def metrics_in(c: dict) -> set[str]:
    k, v = next(iter(c.items()))
    if k in ("all", "any"):
        return set().union(*(metrics_in(s) for s in v))
    if k == "not":
        return metrics_in(v)
    if k in ("wearable", "wearable_level"):
        return {v["metric"]}
    return set()


def _cmp(x: float, op: str, spec: dict) -> bool:
    if op == "gt": return x > spec["value"]
    if op == "ge": return x >= spec["value"]
    if op == "lt": return x < spec["value"]
    if op == "le": return x <= spec["value"]
    if op == "between": return spec["low"] <= x <= spec["high"]
    raise ValueError(op)


def evaluate(c: dict, rep: TrendReport) -> bool:
    """True/False. A missing or paused input makes the condition False, never True."""
    k, v = next(iter(c.items()))
    if k == "all":
        return all(evaluate(s, rep) for s in v)
    if k == "any":
        return any(evaluate(s, rep) for s in v)
    if k == "not":
        return not evaluate(v, rep)
    if k == "fasting":
        return rep.latest_fasting is bool(v)
    if k == "latest":
        t = rep.analytes.get(v["analyte"])
        x = rep.latest_values.get(v["analyte"])   # must come from the newest draw
        if t is None or x is None or t.conflicted:
            return False
        return _cmp(x, v["op"], v)
    if k in ("rising", "falling"):
        t = rep.analytes.get(v["analyte"])
        if t is None or t.conflicted:
            return False
        ch = t.monotonic_change_pct(v.get("draws", 2), "up" if k == "rising" else "down")
        return ch is not None and ch >= v["min_pct"]
    if k == "wearable":
        w = rep.wearables.get(v["metric"])
        if w is None or w.delta_pct is None:
            return False
        d = w.delta_pct
        return (-d if v["direction"] == "down" else d) >= v["min_pct"]
    if k == "wearable_level":
        w = rep.wearables.get(v["metric"])
        if w is None or not w.coverage_ok or w.recent is None:
            return False
        return _cmp(w.recent, v["op"], v)
    raise ValueError(k)


def fill(template: str, rep: TrendReport) -> str:
    vals: dict[str, Any] = {}
    for aid, t in rep.analytes.items():
        if t.latest is not None:
            vals[aid] = f"{t.latest:g}"
        if t.delta_pct is not None:
            vals[f"{aid}_change"] = f"{abs(t.delta_pct):.0f}"
    for m, w in rep.wearables.items():
        if w.recent is not None:
            vals[m] = f"{w.recent:g}"
        if w.delta_pct is not None:
            vals[f"{m}_change"] = f"{abs(w.delta_pct):.0f}"
    try:
        return template.format(**vals)
    except KeyError as e:
        raise ValueError(f"Template needs {e} which is not available") from e
