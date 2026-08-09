"""
Builds an interview coverage plan from the candidate's *actual* mission
data. We only plan around days the candidate completed (passed=True);
skipped or failed days are avoided as interview topics unless nothing
else is available, since probing a candidate on material they explicitly
skipped isn't a fair technical assessment.
"""
from __future__ import annotations

from app.curriculum_loader import get_day, module_for_day
from app.interview_state import MIN_CURRICULUM_DAYS
from app.schemas import Candidate


def _passed_days(candidate: Candidate) -> list[int]:
    return [m.day for m in candidate.missions if m.passed is True]


def _attempted_but_failed_days(candidate: Candidate) -> list[int]:
    return [m.day for m in candidate.missions if m.passed is False]


def build_plan(candidate: Candidate) -> list[int]:
    """
    Returns an ordered list of curriculum day numbers to plan the
    interview around. Guarantees at least MIN_CURRICULUM_DAYS entries
    when the candidate's data supports it, spread across different
    curriculum modules for topic breadth.
    """
    passed = _passed_days(candidate)

    # Prefer spreading across distinct modules for breadth.
    chosen: list[int] = []
    seen_modules: set[int] = set()
    for day in passed:
        mod = module_for_day(day)
        mod_n = mod["n"] if mod else -1
        if mod_n not in seen_modules:
            chosen.append(day)
            seen_modules.add(mod_n)

    # Fill remaining slots with any other passed days not yet chosen,
    # in curriculum order, until we have a healthy pool to draw from.
    remaining = [d for d in passed if d not in chosen]
    chosen.extend(remaining)

    if len(chosen) < MIN_CURRICULUM_DAYS:
        # Candidate passed fewer than 4 missions (rare, edge case).
        # Fall back to attempted-but-failed days so the interview can
        # still meet the minimum coverage requirement; these are
        # explicitly framed as "let's revisit" areas, not gotchas.
        for day in _attempted_but_failed_days(candidate):
            if day not in chosen:
                chosen.append(day)
            if len(chosen) >= MIN_CURRICULUM_DAYS:
                break

    return chosen


def plan_summary(candidate: Candidate) -> list[dict]:
    """Human/UI-friendly view of the plan: day, title, module."""
    plan = build_plan(candidate)
    out = []
    for day in plan:
        d = get_day(day)
        mod = module_for_day(day)
        out.append(
            {
                "day": day,
                "title": d["title"] if d else f"Day {day}",
                "type": d["type"] if d else None,
                "module": mod["title"] if mod else None,
            }
        )
    return out
