from __future__ import annotations

from app.contracts.model_gateway import ModelGatewayRequest


def gateway_request(
    *,
    request_id: str = "request-gateway-001",
    project_id: str = "project-01",
    input_hash: str = "b" * 64,
) -> ModelGatewayRequest:
    return ModelGatewayRequest.model_validate(
        {
            "requestId": request_id,
            "capabilityId": "material_intelligence",
            "mode": "synthetic",
            "trigger": "explicit_action",
            "material": {
                "projectId": project_id,
                "materialId": "material-01",
                "materialVersionId": "material-version-01",
                "contentHash": "a" * 64,
                "mediaKind": "pdf",
                "sourceRef": f"synthetic/{project_id}/material-01",
                "dataClassification": "synthetic_demo",
                "usageAuthorizationRef": None,
            },
            "contextVersion": "context-01",
            "projectContext": {
                "dimensionId": "compliance",
                "industryCode": "synthetic-demo",
                "locale": "zh-CN",
            },
            "fieldSchemas": [
                {
                    "fieldKey": "company_name",
                    "label": "企业名称",
                    "valueType": "string",
                }
            ],
            "taskGoals": ["extract_field_candidates"],
            "inputHash": input_hash,
            "schemaVersion": "1.0",
        }
    )
