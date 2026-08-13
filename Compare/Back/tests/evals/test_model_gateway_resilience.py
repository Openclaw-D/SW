from __future__ import annotations

import asyncio

import pytest

from evals.model_gateway.failure_fixtures import (
    ManualClock,
    run_failure_degradation_fixtures,
)
from evals.model_gateway.resilience import (
    BudgetCeilingExceeded,
    CircuitOpen,
    GatewayResilienceGuard,
    ProviderTimeout,
    RateLimitExceeded,
    ResiliencePolicy,
    RetryableProviderError,
)


def test_all_failure_degradation_fixtures_pass() -> None:
    results = asyncio.run(run_failure_degradation_fixtures())
    assert {item.name for item in results} == {
        "timeout",
        "limited_retry",
        "rate_limit",
        "budget_ceiling",
        "circuit_breaker_recovery",
    }
    assert all(item.passed for item in results)
    assert all(
        item.degraded_to_manual_review
        for item in results
        if item.name != "limited_retry"
    )


def test_retry_is_strictly_limited() -> None:
    calls = 0
    guard = GatewayResilienceGuard(
        ResiliencePolicy(max_retries=2, budget_ceiling_units=3)
    )

    async def always_transient() -> str:
        nonlocal calls
        calls += 1
        raise RetryableProviderError("synthetic transient")

    with pytest.raises(Exception) as error:
        asyncio.run(guard.invoke(always_transient))
    assert error.value.code == "provider_unavailable"
    assert calls == 3


def test_timeout_is_bounded_and_degrades_to_manual_review() -> None:
    guard = GatewayResilienceGuard(
        ResiliencePolicy(timeout_seconds=0.001, max_retries=0)
    )

    async def slow() -> str:
        await asyncio.sleep(0.02)
        return "late"

    with pytest.raises(ProviderTimeout) as error:
        asyncio.run(guard.invoke(slow))
    assert error.value.code == "provider_timeout"
    assert error.value.requires_human_review is True


def test_rate_limit_and_budget_ceiling_do_not_call_operation() -> None:
    rate_clock = ManualClock()
    rate_guard = GatewayResilienceGuard(
        ResiliencePolicy(
            max_retries=0,
            rate_limit_calls=1,
            budget_ceiling_units=10,
        ),
        clock=rate_clock,
    )
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    asyncio.run(rate_guard.invoke(operation))
    with pytest.raises(RateLimitExceeded):
        asyncio.run(rate_guard.invoke(operation))
    assert calls == 1

    budget_guard = GatewayResilienceGuard(
        ResiliencePolicy(max_retries=0, rate_limit_calls=10, budget_ceiling_units=1)
    )
    asyncio.run(budget_guard.invoke(operation))
    with pytest.raises(BudgetCeilingExceeded):
        asyncio.run(budget_guard.invoke(operation))
    assert calls == 2


def test_circuit_opens_without_call_and_recovers_after_timeout() -> None:
    clock = ManualClock()
    guard = GatewayResilienceGuard(
        ResiliencePolicy(
            max_retries=0,
            budget_ceiling_units=3,
            circuit_breaker_threshold=1,
            recovery_timeout_seconds=10,
        ),
        clock=clock,
    )
    calls = 0

    async def fail() -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("synthetic failure")

    async def success() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    with pytest.raises(Exception):
        asyncio.run(guard.invoke(fail))
    with pytest.raises(CircuitOpen):
        asyncio.run(guard.invoke(success))
    assert calls == 1
    clock.advance(10)
    outcome = asyncio.run(guard.invoke(success))
    assert outcome.value == "ok"
    assert calls == 2
    assert guard.circuit_state == "closed"
