from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


SCENARIO_ROOT = Path(__file__).parents[1] / "scenarios" / "assets" / "reference_agent"


def load_reference_scenario(name: str, scenario_id: str | None = None) -> dict[str, Any]:
    """Load a checked-in scenario asset for browser tests."""
    path = SCENARIO_ROOT / name
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    scenarios = document.get("scenarios", [])
    if not scenarios:
        raise ValueError(f"scenario asset {name} contains no scenarios")
    if scenario_id is None:
        return scenarios[0]
    for scenario in scenarios:
        if scenario.get("id") == scenario_id:
            return scenario
    raise ValueError(f"scenario {scenario_id} not found in {name}")


def first_message(name: str, scenario_id: str | None = None) -> str:
    scenario = load_reference_scenario(name, scenario_id)
    return str(scenario["conversation"][0]["user"])


def expected_contains(name: str, scenario_id: str | None = None) -> list[str]:
    scenario = load_reference_scenario(name, scenario_id)
    return list(scenario.get("expect", {}).get("response", {}).get("contains", []))
