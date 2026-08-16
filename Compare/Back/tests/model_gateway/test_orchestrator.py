from __future__ import annotations

import asyncio

import pytest

from app.contracts.errors import IdempotencyConflictError, ServiceError
from app.contracts.material_intelligence import MaterialIntelligenceDataStatus
from app.contracts.model_gateway import ModelGatewayMode
from app.ports.model_gateway import ProviderRateLimitError, ProviderUnavailableError
from app.services.model_gateway import create_model_gateway_service
from app.services.model_gateway.provider_router import SyntheticFakeProvider
from app.services.model_gateway.run_recorder import RunRecorder
from tests.model_gateway.fixtures import gateway_request


class SlowProvider(SyntheticFakeProvider):
    async def execute(self, *args, **kwargs):
        await asyncio.sleep(0.05)
        return await super().execute(*args, **kwargs)


class TimeoutProvider(SyntheticFakeProvider):
    async def execute(self, *args, **kwargs):
        await asyncio.sleep(1)
        return await super().execute(*args, **kwargs)


class RateLimitedProvider(SyntheticFakeProvider):
    async def execute(self, *args, **kwargs):
        self.call_count += 1
        raise ProviderRateLimitError()


class UnavailableProvider(SyntheticFakeProvider):
    async def execute(self, *args, **kwargs):
        self.call_count += 1
        raise ProviderUnavailableError()


class InvalidOutputProvider(SyntheticFakeProvider):
    async def execute(self, *args, **kwargs):
        self.call_count += 1
        return {"advisoryOnly": False}


def test_idempotency_concurrency_and_conflict(tmp_path) -> None:
    provider = SlowProvider()
    service = create_model_gateway_service(
        tmp_path / "gateway.db",
        providers=(provider,),
    )
    request = gateway_request()
    try:
        async def execute_concurrently():
            return await asyncio.gather(
                service.execute(request, idempotency_key="gateway-concurrent-001"),
                service.execute(request, idempotency_key="gateway-concurrent-001"),
            )

        first, second = asyncio.run(execute_concurrently())
        assert first == second
        assert first.advisory_only is True
        assert first.is_simulated is True
        assert provider.call_count == 1

        changed = request.model_copy(update={"input_hash": "c" * 64})
        with pytest.raises(IdempotencyConflictError):
            asyncio.run(
                service.execute(changed, idempotency_key="gateway-concurrent-001")
            )
    finally:
        service.close()


def test_completed_run_replays_after_service_restart(tmp_path) -> None:
    path = tmp_path / "gateway.db"
    provider = SyntheticFakeProvider()
    request = gateway_request()
    service = create_model_gateway_service(path, providers=(provider,))
    first = asyncio.run(
        service.execute(request, idempotency_key="gateway-restart-001")
    )
    service.close()

    restarted_provider = SyntheticFakeProvider()
    restarted = create_model_gateway_service(path, providers=(restarted_provider,))
    try:
        replay = asyncio.run(
            restarted.execute(
                request,
                idempotency_key="gateway-restart-001",
            )
        )
        record = restarted.get_run(request.material.project_id, replay.run_id)
        assert replay == first
        assert restarted_provider.call_count == 0
        assert record.status.value == "needs_review"
        assert record.input_hash == request.input_hash
        assert record.advisory_only is True
        assert record.is_simulated is True
    finally:
        restarted.close()


def test_get_run_projects_real_mode_truth_metadata(tmp_path) -> None:
    recorder = RunRecorder(tmp_path / "gateway-real.db")
    request = gateway_request().model_copy(update={"mode": ModelGatewayMode.REAL})
    try:
        reservation = recorder.reserve(
            request=request,
            idempotency_key="gateway-real-get-run-001",
            request_fingerprint="real-fingerprint-001",
            provider_id="openai_responses",
            lease_seconds=30.0,
        )
        assert reservation.action == "owner"

        record = recorder.get_run(request.material.project_id, reservation.run_id)
        assert record.mode is ModelGatewayMode.REAL
        assert record.advisory_only is True
        assert record.is_simulated is False
        assert record.data_status is (
            MaterialIntelligenceDataStatus.PROVIDER_GENERATED_UNVERIFIED
        )
        assert record.provider_id == "openai_responses"
        assert record.source == "openai_responses"
        assert "不包含原件正文" in record.disclaimer
        assert "绝对路径" in record.disclaimer
        assert "凭据" in record.disclaimer
        assert "人工核验" in record.disclaimer
    finally:
        recorder.close()


@pytest.mark.parametrize(
    ("provider", "code", "status_code"),
    [
        (RateLimitedProvider(), "rate_limited", 429),
        (UnavailableProvider(), "provider_unavailable", 503),
        (InvalidOutputProvider(), "invalid_output", 502),
    ],
)
def test_provider_failures_have_stable_errors(
    tmp_path,
    provider,
    code: str,
    status_code: int,
) -> None:
    service = create_model_gateway_service(
        tmp_path / f"{code}.db",
        providers=(provider,),
    )
    try:
        with pytest.raises(ServiceError) as error:
            asyncio.run(
                service.execute(
                    gateway_request(request_id=f"request-{code}"),
                    idempotency_key=f"gateway-{code}-001",
                )
            )
        assert error.value.code == code
        assert error.value.status_code == status_code
    finally:
        service.close()


def test_timeout_and_budget_exceeded(tmp_path) -> None:
    service = create_model_gateway_service(
        tmp_path / "timeout.db",
        providers=(TimeoutProvider(),),
    )
    service.TIMEOUT_SECONDS = 0.01
    try:
        with pytest.raises(ServiceError) as error:
            asyncio.run(
                service.execute(
                    gateway_request(request_id="request-timeout"),
                    idempotency_key="gateway-timeout-001",
                )
            )
        assert error.value.code == "timeout"
        assert error.value.status_code == 504
    finally:
        service.close()

    budget_service = create_model_gateway_service(tmp_path / "budget.db")
    budget_service.MAX_INPUT_TOKENS = 1
    try:
        with pytest.raises(ServiceError) as error:
            asyncio.run(
                budget_service.execute(
                    gateway_request(request_id="request-budget"),
                    idempotency_key="gateway-budget-001",
                )
            )
        assert error.value.code == "model_budget_exceeded"
        assert error.value.status_code == 422
    finally:
        budget_service.close()
