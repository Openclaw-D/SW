from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.contracts.project_selection import ProjectCatalogItem
from app.contracts.workbench import (
    ApprovalState,
    CommonReviewEvent,
    DIMENSION_IDS,
    ImageMaterial,
    ReviewEvidenceSelectionGroup,
)


def _target(evidence_ref: str) -> dict[str, object]:
    return {
        "evidenceRef": evidence_ref,
        "evidenceRefs": ["ev-1", "ev-2"],
        "dimensionId": "compliance",
        "reviewTargetId": "target-1",
        "factVersionId": "fact-1",
    }


def test_six_dimensions_are_explicit_and_risk_is_not_a_dimension() -> None:
    assert DIMENSION_IDS == (
        "compliance",
        "transaction",
        "production",
        "revenue",
        "debt",
        "cashflow",
    )
    assert "risk" not in DIMENSION_IDS


def test_selection_group_requires_one_consistent_atomic_group() -> None:
    group = ReviewEvidenceSelectionGroup.model_validate(
        {
            "id": "compliance::target-1::fact-1::ev-1::ev-2",
            "dimensionId": "compliance",
            "reviewTargetId": "target-1",
            "factVersionId": "fact-1",
            "targets": [_target("ev-1"), _target("ev-2")],
        }
    )
    assert [item.evidence_ref for item in group.targets] == ["ev-1", "ev-2"]

    invalid = group.model_dump(mode="json", by_alias=True)
    invalid["targets"][1]["evidenceRefs"] = ["ev-2"]
    with pytest.raises(ValidationError, match="complete atomic group"):
        ReviewEvidenceSelectionGroup.model_validate(invalid)


def test_common_event_rejects_client_compatibility_projection_drift() -> None:
    payload = {
        "id": "event-1",
        "projectId": "project-1",
        "sequence": 1,
        "threadId": "thread-1",
        "replyToEventId": None,
        "issueStatus": "open",
        "eventType": "risk_question_submitted",
        "actor": "risk",
        "actorLabel": "风控",
        "dimensionId": "compliance",
        "evidenceTargets": [_target("ev-1"), _target("ev-2")],
        "reviewTargetId": "target-1",
        "title": "问题",
        "summary": "请复核",
        "factVersionIds": ["fact-1"],
        "evidenceRefs": ["ev-1", "ev-2"],
        "ruleRefs": [],
        "createdAt": datetime(2026, 8, 10, tzinfo=UTC).isoformat(),
        "immutable": True,
        "isSimulated": True,
    }
    event = CommonReviewEvent.model_validate(payload)
    assert event.evidence_targets[0].review_target_id == "target-1"

    payload["evidenceRefs"] = ["ev-2", "ev-1"]
    with pytest.raises(ValidationError, match="authoritative evidenceTargets"):
        CommonReviewEvent.model_validate(payload)


def test_completed_approval_can_never_retain_gate_or_risk_veto() -> None:
    blocked = {
        "projectId": "project-1",
        "version": 2,
        "status": "completed",
        "hardGateStatus": "block",
        "blockingRuleIds": ["HG-OWNERSHIP"],
        "riskVeto": True,
        "riskVetoRuleIds": ["RV-001"],
        "updatedAt": datetime(2026, 8, 10, tzinfo=UTC).isoformat(),
        "isSimulated": True,
    }
    with pytest.raises(ValidationError, match="hard gate or risk veto"):
        ApprovalState.model_validate(blocked)


def test_is_simulated_is_boolean_not_schema_constant() -> None:
    schema = ApprovalState.model_json_schema(by_alias=True)
    is_simulated = schema["properties"]["isSimulated"]
    assert is_simulated["type"] == "boolean"
    assert "const" not in is_simulated


def test_project_catalog_risk_band_is_derived_from_risk_level() -> None:
    dimensions = [
        {
            "id": dimension_id,
            "index": index,
            "name": name,
            "fullName": name,
            "score": 80,
            "scoreGrade": "A",
            "confidence": 70,
            "summary": "脱敏规则生成",
        }
        for index, (dimension_id, name) in enumerate(
            zip(DIMENSION_IDS, ("合规", "交易", "生产", "营收", "负债", "流水")),
            1,
        )
    ]
    payload = {
        "projectId": "project-1",
        "projectNo": "SIM-001",
        "companyName": "脱敏制造一号有限公司",
        "companyShortName": "脱敏一号",
        "region": "华东",
        "industry": "装备制造",
        "durationDays": 5,
        "store": "演示门店",
        "salesperson": "演示业务员",
        "amountWan": 500,
        "financingType": "设备融资",
        "materialStatus": "人工复核",
        "createdAt": datetime(2026, 8, 10, tzinfo=UTC).isoformat(),
        "timeBucket": "本月",
        "riskLevel": "confirm",
        "riskBand": "核实",
        "decisionGrade": "B",
        "dimensions": dimensions,
        "isSimulated": True,
    }
    assert ProjectCatalogItem.model_validate(payload).risk_band == "核实"
    payload["riskBand"] = "支持"
    with pytest.raises(ValidationError, match="riskBand"):
        ProjectCatalogItem.model_validate(payload)


def _image_material_payload() -> dict[str, object]:
    return {
        "id": "mat-project-basic-license",
        "versionId": "version-basic-license-v1",
        "fileName": "营业执照.png",
        "label": "营业执照（完整脱敏模拟）",
        "availability": "available",
        "isSimulated": True,
        "sourceLabel": "项目原始材料（完整脱敏模拟）",
        "kind": "image",
        "mimeType": "image/png",
        "pixelWidth": 2048,
        "pixelHeight": 1152,
        "description": "纯虚构演示证照，不含真实主体或证件号码",
        "focalArea": {"x": 0.05, "y": 0.05, "width": 0.9, "height": 0.9},
    }


def test_material_business_paths_are_optional_for_legacy_and_safe_for_p5_originals() -> None:
    legacy = ImageMaterial.model_validate(_image_material_payload())
    assert legacy.business_path is None and legacy.folder_path is None

    current = ImageMaterial.model_validate(
        {
            **_image_material_payload(),
            "folderPath": "基本证照\\营业执照",
            "businessPath": "基本证照\\营业执照\\营业执照.png",
        }
    )
    assert current.folder_path == "基本证照/营业执照"
    assert current.business_path == "基本证照/营业执照/营业执照.png"


@pytest.mark.parametrize(
    ("folder_path", "business_path"),
    [
        ("基本证照", None),
        ("其他资料", "其他资料/营业执照.png"),
        ("基本证照/../增信", "基本证照/../增信/营业执照.png"),
        ("C:/基本证照", "C:/基本证照/营业执照.png"),
        ("基本证照/营业执照", "基本证照/工商核验/营业执照.png"),
    ],
)
def test_material_business_paths_reject_missing_pair_escape_or_parent_drift(
    folder_path: str,
    business_path: str | None,
) -> None:
    payload = {
        **_image_material_payload(),
        "folderPath": folder_path,
    }
    if business_path is not None:
        payload["businessPath"] = business_path
    with pytest.raises(ValidationError):
        ImageMaterial.model_validate(payload)
