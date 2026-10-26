"""Analyte catalog.

One entry per analyte the copilot understands: canonical id, the names labs
print, LOINC code, canonical unit, unit conversions, the lab reference range,
a plausibility window used to catch extraction errors, and critical limits.

All ranges here are ILLUSTRATIVE defaults for a demo with synthetic data.
A real clinic replaces them with its own lab's ranges and its own critical
value policy. Nothing in this file is clinical advice.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Analyte:
    id: str
    display: str
    loinc: str
    unit: str
    aliases: tuple[str, ...]
    ref_low: float | None
    ref_high: float | None
    plausible: tuple[float, float]
    # unit string (lowercased, spaces removed) -> multiplier into canonical unit
    conversions: dict[str, float] = field(default_factory=dict)
    # units that measure something different and cannot be converted
    incompatible_units: tuple[str, ...] = ()
    critical_low: float | None = None
    critical_high: float | None = None
    # analytical tolerance (fraction) used to decide if two close draws conflict
    tolerance: float = 0.10


def _norm_unit(u: str) -> str:
    return u.strip().lower().replace(" ", "").replace("µ", "u").replace("μ", "u")


CATALOG: dict[str, Analyte] = {}


def _add(a: Analyte) -> None:
    conv = {_norm_unit(a.unit): 1.0}
    conv.update({_norm_unit(k): v for k, v in a.conversions.items()})
    object.__setattr__(a, "conversions", conv)
    CATALOG[a.id] = a


_add(Analyte("apob", "Apolipoprotein B", "1884-6", "mg/dL",
             ("apolipoprotein b", "apo b", "apob", "apo-b"),
             None, 90, (10, 400), {"g/L": 100.0}))
_add(Analyte("ldl", "LDL Cholesterol", "13457-7", "mg/dL",
             ("ldl cholesterol", "ldl-c", "ldl chol calc", "ldl cholesterol calc"),
             None, 100, (5, 600), {"mmol/L": 38.67}))
_add(Analyte("hdl", "HDL Cholesterol", "2085-9", "mg/dL",
             ("hdl cholesterol", "hdl-c", "hdl"),
             40, None, (5, 200), {"mmol/L": 38.67}))
_add(Analyte("tg", "Triglycerides", "2571-8", "mg/dL",
             ("triglycerides", "triglyceride", "trig"),
             None, 150, (10, 5000), {"mmol/L": 88.57}))
_add(Analyte("lpa", "Lipoprotein (a)", "43583-4", "nmol/L",
             ("lipoprotein (a)", "lipoprotein(a)", "lp(a)", "lpa"),
             None, 75, (1, 600), {}, incompatible_units=("mg/dl",), tolerance=0.15))
_add(Analyte("a1c", "Hemoglobin A1c", "4548-4", "%",
             ("hemoglobin a1c", "hba1c", "a1c", "glycohemoglobin"),
             None, 5.7, (3, 20), {}, tolerance=0.05))
_add(Analyte("glucose", "Glucose, Fasting", "1558-6", "mg/dL",
             ("glucose", "glucose fasting", "fasting glucose", "glucose, fasting"),
             70, 99, (15, 1500), {"mmol/L": 18.016},
             critical_low=50, critical_high=400))
_add(Analyte("insulin", "Insulin, Fasting", "20448-7", "uIU/mL",
             ("insulin", "insulin fasting", "fasting insulin", "insulin, fasting"),
             2.6, 24.9, (0.5, 300), {"pmol/L": 1 / 6.0, "mIU/L": 1.0}, tolerance=0.20))
_add(Analyte("hscrp", "hs-CRP", "30522-7", "mg/L",
             ("hs-crp", "hs crp", "c-reactive protein, cardiac", "crp high sensitivity", "hscrp"),
             None, 1.0, (0.01, 300), {"mg/dL": 10.0}, tolerance=0.25))
_add(Analyte("vitd", "Vitamin D, 25-OH", "1989-3", "ng/mL",
             ("vitamin d, 25-hydroxy", "vitamin d 25-oh", "25-oh vitamin d", "vitamin d", "25(oh)d"),
             30, 100, (2, 250), {"nmol/L": 1 / 2.496}))
_add(Analyte("ferritin", "Ferritin", "2276-4", "ng/mL",
             ("ferritin",), 30, 400, (1, 5000), {"ug/L": 1.0}, tolerance=0.15))
_add(Analyte("tsh", "TSH", "3016-3", "uIU/mL",
             ("tsh", "thyroid stimulating hormone"),
             0.45, 4.5, (0.005, 150), {"mIU/L": 1.0}, tolerance=0.20))
_add(Analyte("potassium", "Potassium", "2823-3", "mmol/L",
             ("potassium", "k", "potassium, serum"),
             3.5, 5.3, (1.0, 10.0), {"mEq/L": 1.0},
             critical_low=3.0, critical_high=6.0, tolerance=0.05))
_add(Analyte("sodium", "Sodium", "2951-2", "mmol/L",
             ("sodium", "na", "sodium, serum"),
             135, 146, (90, 200), {"mEq/L": 1.0},
             critical_low=125, critical_high=155, tolerance=0.02))
_add(Analyte("creatinine", "Creatinine", "2160-0", "mg/dL",
             ("creatinine", "creatinine, serum"),
             0.6, 1.3, (0.1, 20), {"umol/L": 1 / 88.42}))
_add(Analyte("egfr", "eGFR", "98979-8", "mL/min/1.73m2",
             ("egfr", "estimated gfr", "egfr ckd-epi"),
             60, None, (2, 200), {}))
_add(Analyte("alt", "ALT", "1742-6", "U/L",
             ("alt", "alt (sgpt)", "alanine aminotransferase"),
             None, 46, (2, 5000), {}, tolerance=0.15))
_add(Analyte("hgb", "Hemoglobin", "718-7", "g/dL",
             ("hemoglobin", "hgb", "haemoglobin"),
             12.0, 17.5, (2, 25), {"g/L": 0.1},
             critical_low=7.0, critical_high=20.0, tolerance=0.05))
_add(Analyte("testosterone", "Testosterone, Total", "2986-8", "ng/dL",
             ("testosterone, total", "testosterone total", "total testosterone", "testosterone"),
             264, 916, (2, 3000), {"nmol/L": 28.84}, tolerance=0.15))


_ALIAS_INDEX: dict[str, str] = {}
for _a in CATALOG.values():
    for _name in _a.aliases + (_a.display.lower(), _a.id):
        _ALIAS_INDEX[_name.lower().strip()] = _a.id


def lookup(name: str) -> Analyte | None:
    """Find an analyte by any printed name. Returns None if unknown."""
    key = name.lower().strip().rstrip(":").strip()
    if key in _ALIAS_INDEX:
        return CATALOG[_ALIAS_INDEX[key]]
    return None


def to_canonical(analyte: Analyte, value: float, unit: str) -> tuple[float | None, str]:
    """Convert a value into the analyte's canonical unit.

    Returns (value, status) where status is one of:
      ok, converted, incompatible_unit, unknown_unit, missing_unit
    """
    if not unit or not unit.strip():
        return None, "missing_unit"
    nu = _norm_unit(unit)
    if nu in analyte.incompatible_units:
        return None, "incompatible_unit"
    if nu not in analyte.conversions:
        return None, "unknown_unit"
    factor = analyte.conversions[nu]
    if factor == 1.0:
        return value, "ok"
    return round(value * factor, 3), "converted"
