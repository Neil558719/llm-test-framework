from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


SCENARIO_ROOT = Path(__file__).parents[1] / "scenarios" / "assets" / "reference_agent"


def load_reference_scenario(name: str) -> dict[str, Any]:
    """Load a checked-in scenario asset for browser tests."""
    path = SCENARIO_ROOT / name
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    scenarios = document.get("scenarios", [])
    if not scenarios:
        raise ValueError(f"scenario asset {name} contains no scenarios")
    return scenarios[0]


def first_message(name: str) -> str:
    scenario = load_reference_scenario(name)
    return str(scenario["conversation"][0]["user"])
