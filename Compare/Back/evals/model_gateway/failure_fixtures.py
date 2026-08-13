"""Deterministic degradation scenarios used by the offline release Gate."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .resilience import (
    BudgetCeilingExceeded,
    CircuitOpen,
    GatewayResilienceGuard,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimitExceeded,
    ResiliencePolicy,
    RetryableProviderError,
)


@dataclass(frozen=True, slots=True)
class FailureScenarioResult:
    name: str
    passed: bool
    degraded_to_manual_review: bool


class ManualClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


async def run_failure_degradation_fixtures() -> tuple[FailureScenarioResult, ...]:
    results = [
        await _timeout_fixture(),
        await _limited_retry_fixture(),
        await _rate_limit_fixture(),
        await _budget_fixture(),
        await _circuit_recovery_fixture(),
    ]
    return tuple(results)


async def _timeout_fixture() -> FailureScenarioResult:
    guard = GatewayResilienceGuard(
        ResiliencePolicy(timeout_seconds=0.001, max_retries=1, budget_ceiling_units=2)
    )

    async def slow() -> str:
        await asyncio.sleep(0.02)
        return "late"

    try:
        await guard.invoke(slow)
    except ProviderTimeout as error:
        return FailureScenarioResult("timeout", True, error.requires_human_review)
    return FailureScenarioResult("timeout", False, False)


async def _limited_retry_fixture() -> FailureScenarioResult:
    guard = GatewayResilienceGuard(
        ResiliencePolicy(max_retries=1, budget_ceiling_units=2)
    )
    calls = 0

    async def transient_then_success() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RetryableProviderError("synthetic transient")
        return "recovered"

    outcome = await guard.invoke(transient_then_success)
    return FailureScenarioResult(
        "limited_retry", outcome.value == "recovered" and outcome.attempts == 2, False
    )


async def _rate_limit_fixture() -> FailureScenarioResult:
    clock = ManualClock()
    guard = GatewayResilienceGuard(
        ResiliencePolicy(
            max_retries=0,
            rate_limit_calls=1,
            rate_limit_period_seconds=60,
            budget_ceiling_units=2,
        ),
        clock=clock,
    )

    async def success() -> str:
        return "ok"

    await guard.invoke(success)
    try:
        await guard.invoke(success)
    except RateLimitExceeded as error:
        return FailureScenarioResult("rate_limit", True, error.requires_human_review)
    return FailureScenarioResult("rate_limit", False, False)


async def _budget_fixture() -> FailureScenarioResult:
    guard = GatewayResilienceGuard(
        ResiliencePolicy(max_retries=0, rate_limit_calls=10, budget_ceiling_units=1)
    )

    async def success() -> str:
        return "ok"

    await guard.invoke(success)
    try:
        await guard.invoke(success)
    except BudgetCeilingExceeded as error:
        return FailureScenarioResult("budget_ceiling", True, error.requires_human_review)
    return FailureScenarioResult("budget_ceiling", False, False)


async def _circuit_recovery_fixture() -> FailureScenarioResult:
    clock = ManualClock()
    guard = GatewayResilienceGuard(
        ResiliencePolicy(
            max_retries=0,
            budget_ceiling_units=3,
            circuit_breaker_threshold=1,
            recovery_timeout_seconds=5,
        ),
        clock=clock,
    )

    async def fail() -> str:
        raise RuntimeError("synthetic hard failure")

    async def success() -> str:
        return "recovered"

    first_failed = False
    open_rejected = False
    try:
        await guard.invoke(fail)
    except ProviderUnavailable as error:
        first_failed = error.requires_human_review
    try:
        await guard.invoke(success)
    except CircuitOpen as error:
        open_rejected = error.requires_human_review
    clock.advance(5)
    outcome = await guard.invoke(success)
    passed = (
        first_failed
        and open_rejected
        and outcome.value == "recovered"
        and guard.circuit_state == "closed"
    )
    return FailureScenarioResult("circuit_breaker_recovery", passed, first_failed)
