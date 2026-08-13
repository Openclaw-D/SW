from __future__ import annotations

import asyncio

import pytest

from app.contracts.errors import BusinessValidationError, ServiceError
from app.contracts.material_intelligence import DataClassification
from app.contracts.model_gateway import ModelGatewayMode
from app.services.model_gateway.capability_registry import CapabilityRegistry
from app.services.model_gateway.input_assembler import assemble_input
from app.services.model_gateway.output_validator import validate_output
from app.services.model_gateway.provider_router import SyntheticFakeProvider
from tests.model_gateway.fixtures import gateway_request


def test_registry_exposes_only_advisory_synthetic_capability() -> None:
    registry = CapabilityRegistry()
    capabilities = registry.list()

    assert [item.capability_id for item in capabilities] == ["material_intelligence"]
    assert capabilities[0].advisory_only is True
    assert capabilities[0].supported_modes == [ModelGatewayMode.SYNTHETIC]


def test_assembler_contains_no_answer_or_original_content_and_rejects_paths() -> None:
    request = gateway_request()
    capability = CapabilityRegistry().require(request.capability_id)
    assembled = assemble_input(request, capability, max_input_tokens=8_000)
    serialized = str(assembled.payload).lower()

    assert assembled.input_hash == request.input_hash
    assert "expectedanswer" not in serialized
    assert "groundtruth" not in serialized
    assert "originalcontent" not in serialized
    assert "c:\\" not in serialized

    unsafe = request.model_copy(
        update={
            "material": request.material.model_copy(
                update={"source_ref": r"C:\private\customer.pdf"}
            )
        }
    )
    with pytest.raises(BusinessValidationError) as error:
        assemble_input(unsafe, capability, max_input_tokens=8_000)
    assert error.value.code == "request_invalid"


def test_assembler_rejects_real_or_non_synthetic_material_and_budget() -> None:
    request = gateway_request()
    capability = CapabilityRegistry().require(request.capability_id)

    real = request.model_copy(update={"mode": ModelGatewayMode.REAL})
    with pytest.raises(BusinessValidationError) as error:
        assemble_input(real, capability, max_input_tokens=8_000)
    assert error.value.code == "real_provider_not_enabled"

    customer = request.model_copy(
        update={
            "material": request.material.model_copy(
                update={
                    "data_classification": DataClassification.AUTHORIZED_CUSTOMER,
                    "usage_authorization_ref": "authorization-01",
                }
            )
        }
    )
    with pytest.raises(BusinessValidationError) as error:
        assemble_input(customer, capability, max_input_tokens=8_000)
    assert error.value.code == "authorization_required"

    with pytest.raises(BusinessValidationError) as error:
        assemble_input(request, capability, max_input_tokens=1)
    assert error.value.code == "model_budget_exceeded"


def test_strict_validator_rejects_authority_or_binding_drift() -> None:
    request = gateway_request()
    capability = CapabilityRegistry().require(request.capability_id)
    assembled = assemble_input(request, capability, max_input_tokens=8_000)
    provider = SyntheticFakeProvider()
    valid = asyncio.run(
        provider.execute(request, assembled, max_output_tokens=2_000)
    )

    assert validate_output(valid, request=request, provider_id=provider.provider_id)

    invalid = valid.model_dump(mode="json", by_alias=True)
    invalid["advisoryOnly"] = False
    with pytest.raises(ServiceError) as error:
        validate_output(invalid, request=request, provider_id=provider.provider_id)
    assert error.value.code == "invalid_output"

    invalid = valid.model_dump(mode="json", by_alias=True)
    invalid["inputHash"] = "c" * 64
    with pytest.raises(ServiceError) as error:
        validate_output(invalid, request=request, provider_id=provider.provider_id)
    assert error.value.code == "invalid_output"
