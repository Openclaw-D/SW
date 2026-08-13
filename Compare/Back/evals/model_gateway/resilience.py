"""Eval-only resilience guard with deterministic, dependency-free controls."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, TypeVar


T = TypeVar("T")


class RetryableProviderError(RuntimeError):
    """A fake/provider-declared transient failure eligible for limited retry."""


class ResilienceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.requires_human_review = True


class ProviderTimeout(ResilienceError):
    def __init__(self) -> None:
        super().__init__("provider_timeout", "provider timed out; manual review required")


class ProviderUnavailable(ResilienceError):
    def __init__(self) -> None:
        super().__init__(
            "provider_unavailable", "provider unavailable; manual review required"
        )


class RateLimitExceeded(ResilienceError):
    def __init__(self) -> None:
        super().__init__("rate_limit_exceeded", "rate limit reached; manual review required")


class BudgetCeilingExceeded(ResilienceError):
    def __init__(self) -> None:
        super().__init__(
            "budget_ceiling_exceeded", "budget ceiling reached; manual review required"
        )


class CircuitOpen(ResilienceError):
    def __init__(self) -> None:
        super().__init__("circuit_open", "circuit is open; manual review required")


@dataclass(frozen=True, slots=True)
class ResiliencePolicy:
    timeout_seconds: float = 10.0
    max_retries: int = 1
    retry_delay_seconds: float = 0.0
    rate_limit_calls: int = 10
    rate_limit_period_seconds: float = 60.0
    budget_ceiling_units: float = 10.0
    circuit_breaker_threshold: int = 3
    recovery_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0 or self.max_retries > 3:
            raise ValueError("max_retries must be between 0 and 3")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must not be negative")
        if self.rate_limit_calls <= 0 or self.rate_limit_period_seconds <= 0:
            raise ValueError("rate limit must be positive")
        if self.budget_ceiling_units <= 0:
            raise ValueError("budget_ceiling_units must be positive")
        if self.circuit_breaker_threshold <= 0:
            raise ValueError("circuit_breaker_threshold must be positive")
        if self.recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ResilienceOutcome(Generic[T]):
    value: T
    attempts: int
    spent_units: float


class GatewayResilienceGuard:
    """Bound calls without importing or mutating production gateway state."""

    def __init__(
        self,
        policy: ResiliencePolicy,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.policy = policy
        self._clock = clock
        self._sleep = sleep
        self._call_times: deque[float] = deque()
        self._spent_units = 0.0
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def spent_units(self) -> float:
        return self._spent_units

    @property
    def circuit_state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self.policy.recovery_timeout_seconds:
            return "half_open"
        return "open"

    async def invoke(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        cost_units: float = 1.0,
    ) -> ResilienceOutcome[T]:
        if cost_units <= 0:
            raise ValueError("cost_units must be positive")
        state = self.circuit_state
        if state == "open":
            raise CircuitOpen()

        last_failure: str | None = None
        for attempt in range(1, self.policy.max_retries + 2):
            self._admit_attempt(cost_units)
            try:
                value = await asyncio.wait_for(
                    operation(), timeout=self.policy.timeout_seconds
                )
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                last_failure = "timeout"
            except RetryableProviderError:
                last_failure = "unavailable"
            except Exception as error:
                self._record_failed_invocation()
                raise ProviderUnavailable() from error
            else:
                self._record_success()
                return ResilienceOutcome(
                    value=value,
                    attempts=attempt,
                    spent_units=self._spent_units,
                )

            if attempt <= self.policy.max_retries:
                await self._sleep(self.policy.retry_delay_seconds)

        self._record_failed_invocation()
        if last_failure == "timeout":
            raise ProviderTimeout()
        raise ProviderUnavailable()

    def _admit_attempt(self, cost_units: float) -> None:
        now = self._clock()
        cutoff = now - self.policy.rate_limit_period_seconds
        while self._call_times and self._call_times[0] <= cutoff:
            self._call_times.popleft()
        if len(self._call_times) >= self.policy.rate_limit_calls:
            raise RateLimitExceeded()
        if self._spent_units + cost_units > self.policy.budget_ceiling_units:
            raise BudgetCeilingExceeded()
        self._call_times.append(now)
        self._spent_units += cost_units

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def _record_failed_invocation(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.policy.circuit_breaker_threshold:
            self._opened_at = self._clock()
