from __future__ import annotations

from app.contracts.errors import BusinessValidationError
from app.contracts.material_intelligence import MaterialMediaKind
from app.contracts.model_gateway import (
    ModelGatewayCapability,
    ModelGatewayMode,
    ModelGatewayOutputKind,
)


class CapabilityRegistry:
    def __init__(
        self,
        definitions: tuple[ModelGatewayCapability, ...] | None = None,
    ) -> None:
        definitions = definitions or (
            ModelGatewayCapability(
                capability_id="material_intelligence",
                provider_id="synthetic_fake",
                supported_modes=[ModelGatewayMode.SYNTHETIC],
                input_kinds=list(MaterialMediaKind),
                output_kinds=[
                    ModelGatewayOutputKind.OBSERVATIONS,
                    ModelGatewayOutputKind.FIELD_CANDIDATES,
                    ModelGatewayOutputKind.SOURCE_ANCHORS,
                    ModelGatewayOutputKind.SCENE_SPEC,
                ],
                advisory_only=True,
            ),
        )
        self._definitions = {item.capability_id: item for item in definitions}
        if len(self._definitions) != len(definitions):
            raise ValueError("capabilityId values must be unique")

    def list(self) -> list[ModelGatewayCapability]:
        return [self._definitions[key] for key in sorted(self._definitions)]

    def require(self, capability_id: str) -> ModelGatewayCapability:
        definition = self._definitions.get(capability_id)
        if definition is None:
            raise BusinessValidationError(
                "capability_not_supported",
                "请求的 Model Gateway capability 未注册。",
                field="capabilityId",
                details={"capabilityId": capability_id},
            )
        return definition
