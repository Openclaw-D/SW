"""Hard-off-by-default policy for any future real-provider evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


LIVE_POLICY_PATH = Path(__file__).with_name("data") / "live_eval_policy.json"
LIVE_ACKNOWLEDGEMENT = "P5_MG_LIVE_EVAL_EXPLICITLY_AUTHORIZED"


@dataclass(frozen=True, slots=True)
class LiveEvalPolicy:
    enabled: bool
    max_calls: int
    budget_ceiling_units: float
    acknowledgement: str | None

    def assert_allowed(self) -> None:
        if not self.enabled:
            raise PermissionError("real-provider evaluation is disabled")
        if self.acknowledgement != LIVE_ACKNOWLEDGEMENT:
            raise PermissionError("real-provider evaluation lacks explicit acknowledgement")
        if self.max_calls <= 0:
            raise ValueError("enabled real-provider evaluation requires maxCalls > 0")
        if self.budget_ceiling_units <= 0:
            raise ValueError(
                "enabled real-provider evaluation requires budgetCeilingUnits > 0"
            )


def load_live_eval_policy(path: Path = LIVE_POLICY_PATH) -> LiveEvalPolicy:
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    policy = LiveEvalPolicy(
        enabled=payload.get("enabled") is True,
        max_calls=int(payload.get("maxCalls", 0)),
        budget_ceiling_units=float(payload.get("budgetCeilingUnits", 0)),
        acknowledgement=payload.get("acknowledgement"),
    )
    if not policy.enabled and (policy.max_calls != 0 or policy.budget_ceiling_units != 0):
        raise ValueError("disabled real-provider policy must have zero calls and zero budget")
    return policy
