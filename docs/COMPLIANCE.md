# Regulatory design notes

This is a design note, not legal advice. Anyone deploying this in a clinic needs regulatory counsel.

## The line we design around

FDA's guidance on Clinical Decision Support (CDS) software was revised on **January 6, 2026**. It keeps the four criteria from the 21st Century Cures Act that separate non-device CDS from regulated device software. Software must meet all four:

| # | Criterion | How Protocol Copilot meets it |
|---|---|---|
| 1 | Does not acquire, process or analyse a medical image, an IVD signal, or a pattern or signal from a signal acquisition system | Reads finished, discrete lab results as printed on a report. Uses wearable **daily summaries** only (nightly HRV average, resting HR, sleep hours, steps). Never touches raw PPG, ECG or accelerometer streams |
| 2 | Displays, analyses or prints medical information | Lab values, trends and the clinic's own protocol text |
| 3 | Supports or provides recommendations to a health care professional | Output is a draft plan for a clinician. Nothing reaches a member without clinician approval. Never names a diagnosis |
| 4 | The professional can independently review the basis and is not meant to rely primarily on it | Every item shows the rule id, the exact values that triggered it, and the guideline or clinic policy behind it. Rules are plain YAML anyone can read |

## Guardrails in code, not in policy docs

- **Critical values bypass everything.** Fixed thresholds, no model. A critical value blocks the member summary until a clinician confirms the member was contacted (`critical_contact_logged`).
- **Not time critical.** Prep happens before a scheduled visit. The 2026 guidance treats time-critical use as failing criterion 4. Critical values are routed to a human, not handled by the tool.
- **No diagnosis.** Clinician text cites guideline bands ("A1c in the 5.7 to 6.4% band defined in ADA criteria"). Member text is checked against a banned word list that includes condition names and scores.
- **Paused, not guessed.** Conflicting draws, non-comparable units, missing units and implausible values stop the related rules and raise a flag.
- **Sources are accepted guidelines.** The 2026 guidance expects recommendations to rest on well understood sources. Each rule names one. Clinic preferences are labelled as such.
- **The LLM never decides.** It may transcribe an unfamiliar PDF layout. Its output goes through the same unit and plausibility checks as the deterministic parser. Rules fire in code.

## Open questions for counsel

- How FDA would view lab values pulled from PDFs under criterion 1. FDA examples have treated discrete lab results as medical information, but this should be confirmed for the specific product.
- Whether the member-facing summary, which only restates clinician-approved items, needs separate review under FDA's general wellness policy (also updated January 2026).
- HIPAA: a real deployment processes PHI and needs a BAA with every vendor in the path, including any LLM provider.

## Sources
- [Covington: 5 key takeaways from FDA's revised CDS guidance (Jan 2026)](https://www.cov.com/en/news-and-insights/insights/2026/01/5-key-takeaways-from-fdas-revised-clinical-decision-support-cds-software-guidance)
- [Cooley: FDA makes incremental updates to CDS guidance](https://www.cooley.com/news/insight/2026/2026-01-20-automation-bias-and-clinical-practice-fda-makes-incremental-updates-to-clinical-decision-support-software-guidance)
- [FDA guidance document](https://www.fda.gov/media/191561/download)
