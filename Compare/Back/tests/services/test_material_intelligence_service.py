from __future__ import annotations

import asyncio

import pytest

from app.contracts.errors import BusinessValidationError, ServiceError
from app.contracts.material_intelligence import MaterialIntelligenceRequest
from app.services.material_intelligence import (
    MaterialIntelligenceHarnessConfig,
    execute_material_intelligence,
)


def _request() -> MaterialIntelligenceRequest:
    return MaterialIntelligenceRequest(
        projectId="project-a", materialId="material-a",
        materialVersionId="material-a-v1", contentHash="a" * 64,
        mediaKind="image", contextVersion="context-v1",
        taskGoals=["observe"], dataClassification="synthetic_demo",
        usageAuthorizationRef="synthetic-test",
    )


class InvalidProvider:
    async def analyze(self, request, context, input_hash):
        return {"unexpected": True}


class SlowProvider:
    async def analyze(self, request, context, input_hash):
        await asyncio.sleep(0.05)
        return {}


def test_material_intelligence_disabled_stops_before_provider_call() -> None:
    with pytest.raises(BusinessValidationError) as error:
        asyncio.run(execute_material_intelligence(
            _request(), {"fieldKey": "registration_valid"}, InvalidProvider(),
            MaterialIntelligenceHarnessConfig(enabled=False, timeout_seconds=1),
        ))
    assert error.value.code == "material_intelligence_disabled"


def test_material_intelligence_timeout_isolated_as_stable_504() -> None:
    with pytest.raises(ServiceError) as error:
        asyncio.run(execute_material_intelligence(
            _request(), {"fieldKey": "registration_valid"}, SlowProvider(),
            MaterialIntelligenceHarnessConfig(enabled=True, timeout_seconds=0.001),
        ))
    assert error.value.code == "material_intelligence_timeout"
    assert error.value.status_code == 504


def test_material_intelligence_invalid_output_is_discarded() -> None:
    with pytest.raises(ServiceError) as error:
        asyncio.run(execute_material_intelligence(
            _request(), {"fieldKey": "registration_valid"}, InvalidProvider(),
            MaterialIntelligenceHarnessConfig(enabled=True, timeout_seconds=1),
        ))
    assert error.value.code == "material_intelligence_invalid_output"
    assert error.value.status_code == 502
