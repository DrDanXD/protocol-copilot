"""Member-facing summary, written ONLY from the clinician-approved plan.

Calm language. No scores. No condition names. At most three next steps.
If the plan carries a critical flag, no summary is produced: a person calls.
"""
from __future__ import annotations

import re

from .schema import DraftPlan, MemberSummary, PlanItem

BANNED = [
    r"abnormal", r"critical", r"disease", r"diagnos", r"pre-?diabet", r"diabet", r"deficien",
    r"\bscore\b", r"risk score", r"failure", r"cancer", r"danger", r"alarming", r"high risk",
    r"\burgent", r"\bworse\b", r"\bbad\b", r"organ age", r"biological age",
]
_BANNED_RE = re.compile("|".join(BANNED), re.I)

POSITIVE_RULES = {"LIPID-06"}  # rules that report an improvement

CATEGORY_ORDER = {"refer": 0, "retest": 1, "discuss": 2, "lifestyle": 3, "monitor": 4}


def banned_terms(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in _BANNED_RE.finditer(text)})


def member_summary(plan: DraftPlan, approved: list[PlanItem] | None = None,
                   first_name: str = "", contacted: bool = False) -> MemberSummary:
    """`approved` is the clinician-edited item list. Defaults to the draft for previews.

    A plan with a critical value stays held until the clinician confirms they spoke
    with the member (`contacted`). Even then the summary never says results look steady.
    """
    critical = plan.status == "blocked_critical" or any(f.kind == "critical" for f in plan.flags)
    if critical and not contacted:
        return MemberSummary(member_id=plan.member_id, blocked=True,
                             headline="Held for clinician contact",
                             body=["A clinician needs to speak with this member before any written summary goes out."])
    if any(f.kind == "not_measured" for f in plan.flags):
        return MemberSummary(member_id=plan.member_id, blocked=True, headline="No lab results on file",
                             body=["Nothing to summarise until a draw is added."])
    items = [i for i in (approved if approved is not None else plan.items)
             if i.member_text and i.rule_id != "CRITICAL"]
    items.sort(key=lambda i: (i.priority, CATEGORY_ORDER.get(i.category, 9)))
    wins = [i for i in items if i.rule_id in POSITIVE_RULES]
    actions = [i for i in items if i not in wins]

    hi = f"Hi {first_name}. " if first_name else ""
    followup = "We will follow up on the result we discussed on the phone."
    if critical and not actions and not wins:
        return MemberSummary(member_id=plan.member_id, headline=f"{hi}Thanks for talking with us today.",
                             body=[followup])
    if not actions and wins:
        headline = f"{hi}Good progress since your last visit."
    elif not actions:
        headline = f"{hi}Your results look steady."
    elif wins:
        headline = f"{hi}Some good progress, and a few small things to work on."
    else:
        headline = f"{hi}Here is your plan until we next meet."

    body = [w.member_text for w in wins[:1]]
    if critical:
        body.append(followup)
    if any(i.category in ("retest", "refer") for i in actions):
        body.append("We will repeat a test or two. That is routine and helps us be sure.")
    if any(i.category == "discuss" for i in actions):
        body.append("Your clinician will go through a couple of results with you at your visit.")

    steps: list[str] = []
    for i in actions:
        if i.member_text not in steps:
            steps.append(i.member_text)
    summary = MemberSummary(member_id=plan.member_id, headline=headline, body=body[:3],
                            next_steps=steps[:3])
    bad = banned_terms(" ".join([summary.headline, *summary.body, *summary.next_steps]))
    if bad:
        # Never ship wording the clinic has ruled out. Surface it for a human instead.
        return MemberSummary(member_id=plan.member_id, blocked=True, headline="Needs rewording",
                             body=[f"Contains words not allowed in member messages: {', '.join(bad)}"])
    return summary
