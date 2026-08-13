"""Two-phase P5 ModelGateway offline evaluation runner."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .dataset import assert_dataset_alignment, load_hidden_truth, load_public_cases
from .failure_fixtures import run_failure_degradation_fixtures
from .fake_provider import OfflineSyntheticFakeProvider
from .live_policy import load_live_eval_policy
from .metrics import aggregate_metrics, evaluate_case


async def run_offline_eval() -> dict[str, Any]:
    live_policy = load_live_eval_policy()
    if live_policy.enabled:
        raise RuntimeError("offline runner refuses enabled real-provider policy")

    public_cases = load_public_cases()
    hidden_truth = load_hidden_truth()
    assert_dataset_alignment(public_cases, hidden_truth)
    provider = OfflineSyntheticFakeProvider()

    smoke_cases = tuple(case for case in public_cases if case.smoke)
    smoke_outputs = [await provider.predict(case.provider_input) for case in smoke_cases]
    _assert_no_hidden_truth_at_provider_boundary(provider.received_inputs)
    smoke_metrics = aggregate_metrics(
        evaluate_case(
            case,
            output,
            hidden_truth[case.case_id],
            provider_advisory_only=provider.advisory_only,
        )
        for case, output in zip(smoke_cases, smoke_outputs, strict=True)
    )

    if not smoke_metrics["passed"]:
        return _report(
            provider,
            smoke_metrics=smoke_metrics,
            standard_metrics=None,
            failure_results=(),
            release_gate=False,
            blocked_by="six_industry_smoke_gate",
        )

    standard_outputs = [
        await provider.predict(case.provider_input) for case in public_cases
    ]
    _assert_no_hidden_truth_at_provider_boundary(provider.received_inputs)
    standard_metrics = aggregate_metrics(
        evaluate_case(
            case,
            output,
            hidden_truth[case.case_id],
            provider_advisory_only=provider.advisory_only,
        )
        for case, output in zip(public_cases, standard_outputs, strict=True)
    )
    failure_results = await run_failure_degradation_fixtures()
    failure_rate = round(
        sum(item.passed for item in failure_results) / len(failure_results), 6
    )
    release_gate = standard_metrics["passed"] and failure_rate == 1.0
    return _report(
        provider,
        smoke_metrics=smoke_metrics,
        standard_metrics=standard_metrics,
        failure_results=failure_results,
        release_gate=release_gate,
        blocked_by=None if release_gate else "standard_or_resilience_gate",
    )


def _report(
    provider: OfflineSyntheticFakeProvider,
    *,
    smoke_metrics: dict[str, Any],
    standard_metrics: dict[str, Any] | None,
    failure_results: tuple[Any, ...],
    release_gate: bool,
    blocked_by: str | None,
) -> dict[str, Any]:
    failure_rate = (
        round(sum(item.passed for item in failure_results) / len(failure_results), 6)
        if failure_results
        else 0.0
    )
    return {
        "task": "P5-MG-EvalRelease",
        "mode": "offline_synthetic_fake",
        "isSimulated": True,
        "dataStatus": "synthetic_demo",
        "source": "deterministic_offline_eval_fixture",
        "disclaimer": "脱敏合成离线评测；未调用真实 provider，不代表统计模型有效性。",
        "advisoryOnly": provider.advisory_only,
        "realProviderCalled": False,
        "providerCallCount": provider.calls,
        "phases": {
            "sixIndustrySmoke": smoke_metrics,
            "twentyFourProjectStandard": standard_metrics,
        },
        "failureDegradation": {
            "rate": failure_rate,
            "scenarios": [asdict(item) for item in failure_results],
        },
        "releaseGatePassed": release_gate,
        "blockedBy": blocked_by,
    }


def _assert_no_hidden_truth_at_provider_boundary(inputs: list[Any]) -> None:
    forbidden = {"expectedFields", "goldenTruth", "hiddenTruth"}
    for item in inputs:
        serialized = json.dumps(dict(item), ensure_ascii=False, sort_keys=True)
        if any(key in serialized for key in forbidden):
            raise AssertionError("hidden golden truth crossed the provider boundary")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    arguments = parser.parse_args()
    report = asyncio.run(run_offline_eval())
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["releaseGatePassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
