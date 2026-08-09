"""
Loads candidates.json (the hackathon-supplied source of truth) for the
frontend's candidate-selection screens. The /api/interview endpoint
itself never reads this file - it uses whatever candidate object the
client sends, per the Technical Specification.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "candidates.json"


@lru_cache(maxsize=1)
def load_candidates() -> dict[str, Any]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def list_candidates() -> list[dict[str, Any]]:
    return load_candidates()["candidates"]
