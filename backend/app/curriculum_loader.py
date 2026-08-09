"""
Loads curriculum.json (the hackathon-supplied source of truth) once at
startup and exposes small lookup helpers used by the interview planner
and question engine.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "curriculum.json"


@lru_cache(maxsize=1)
def load_curriculum() -> dict[str, Any]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def days_by_number() -> dict[int, dict[str, Any]]:
    curriculum = load_curriculum()
    return {d["day"]: d for d in curriculum["days"]}


def get_day(day_number: int) -> dict[str, Any] | None:
    return days_by_number().get(day_number)


def modules() -> list[dict[str, Any]]:
    return load_curriculum()["modules"]


def module_for_day(day_number: int) -> dict[str, Any] | None:
    for m in modules():
        start, end = m["days"]
        if start <= day_number <= end:
            return m
    return None


def cohort_name() -> str:
    return load_curriculum().get("cohort", "AI Cohort")
