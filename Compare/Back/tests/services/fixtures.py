from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.contracts.workbench import DimensionSeriesRequest
from app.domain.constants import RULE_VERSION
from app.services.generator_adapter import GeneratedProjectBundle


DIMENSIONS = (
    ("compliance", 1, "合规", "主体合规", "subject-network"),
    ("transaction", 2, "交易", "交易结构", "transaction-structure"),
    ("production", 3, "生产", "生产经营", "production-series"),
    ("revenue", 4, "营收", "营收表现", "revenue-series"),
    ("debt", 5, "负债", "负债结构", "debt-structure"),
    ("cashflow", 6, "流水", "资金流水", "cashflow-series"),
)


def _dimensions() -> list[dict[str, Any]]:
    return [
        {
            "id": dimension_id,
            "index": index,
            "name": name,
            "fullName": full_name,
            "score": 80,
            "scoreGrade": "A",
            "confidence": 80,
            "summary": f"{name}脱敏规则结果",
        }
        for dimension_id, index, name, full_name, _visual in DIMENSIONS
    ]


def _dimension_details() -> list[dict[str, Any]]:
    return [
        {
            "dimensionId": dimension_id,
            "visual": visual,
            "defaultView": "visual",
            "availableViews": ["visual", "table"],
            "unit": "",
            "metrics": [],
            "series": [],
            "breakdown": [],
            "conclusion": f"{name}规则结论",
            "sourceLabel": "测试生成器",
            "isSimulated": True,
        }
        for dimension_id, _index, name, _full_name, visual in DIMENSIONS
    ]


def _materials(project_id: str) -> list[dict[str, Any]]:
    prefix = project_id
    return [
        {
            "id": f"{prefix}-excel",
            "versionId": f"{prefix}-excel-v1",
            "fileName": "脱敏台账.xlsx",
            "label": "脱敏台账",
            "availability": "available",
            "isSimulated": True,
            "sourceLabel": "测试生成器",
            "kind": "excel",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "sheets": [
                {
                    "name": "主体",
                    "columns": ["字段", "值"],
                    "rows": [["统一社会信用代码", "TEST-001"], ["状态", "正常"]],
                }
            ],
        },
        {
            "id": f"{prefix}-pdf",
            "versionId": f"{prefix}-pdf-v1",
            "fileName": "脱敏合同.pdf",
            "label": "脱敏合同",
            "availability": "available",
            "isSimulated": True,
            "sourceLabel": "测试生成器",
            "kind": "pdf",
            "mimeType": "application/pdf",
            "pageCount": 1,
            "pages": [{"page": 1, "title": "合同", "lines": ["脱敏条款"]}],
        },
        {
            "id": f"{prefix}-image",
            "versionId": f"{prefix}-image-v1",
            "fileName": "脱敏现场.png",
            "label": "脱敏现场",
            "availability": "available",
            "isSimulated": True,
            "sourceLabel": "测试生成器",
            "kind": "image",
            "mimeType": "image/png",
            "pixelWidth": 1000,
            "pixelHeight": 800,
            "description": "脱敏现场示意",
            "focalArea": {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5},
        },
        {
            "id": f"{prefix}-media",
            "versionId": f"{prefix}-media-v1",
            "fileName": "脱敏视频.mp4",
            "label": "脱敏视频",
            "availability": "available",
            "isSimulated": True,
            "sourceLabel": "测试生成器",
            "kind": "media",
            "mimeType": "video/mp4",
            "mediaKind": "video",
            "durationSeconds": 10,
            "description": "脱敏视频示意",
            "posterMaterialId": f"{prefix}-image",
        },
        {
            "id": f"{prefix}-scene",
            "versionId": f"{prefix}-scene-v1",
            "fileName": "脱敏场景.json",
            "label": "脱敏场景",
            "availability": "available",
            "isSimulated": True,
            "sourceLabel": "测试生成器",
            "kind": "scene",
            "mimeType": "application/vnd.compare.gaussian-scene+json",
            "sceneFormat": "compare-gaussian-preview-v1",
            "points": [
                {"id": "point-1", "x": 0, "y": 0, "z": 0, "size": 1, "color": "#ffffff"}
            ],
            "fallbackMaterialId": f"{prefix}-image",
            "description": "脱敏场景示意",
        },
    ]


def _evidence(project_id: str) -> list[dict[str, Any]]:
    prefix = project_id
    return [
        {
            "id": f"{prefix}-ev-excel",
            "label": "Excel 字段",
            "locator": {
                "kind": "excel",
                "materialId": f"{prefix}-excel",
                "materialVersionId": f"{prefix}-excel-v1",
                "sheet": "主体",
                "range": "A4:B4",
            },
            "locationStatus": "located",
            "materialStatus": "confirmed",
        },
        {
            "id": f"{prefix}-ev-pdf",
            "label": "PDF 条款",
            "locator": {
                "kind": "pdf",
                "materialId": f"{prefix}-pdf",
                "materialVersionId": f"{prefix}-pdf-v1",
                "page": 1,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.2},
            },
            "locationStatus": "located",
            "materialStatus": "confirmed",
        },
        {
            "id": f"{prefix}-ev-image",
            "label": "图片区域",
            "locator": {
                "kind": "image",
                "materialId": f"{prefix}-image",
                "materialVersionId": f"{prefix}-image-v1",
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5},
            },
            "locationStatus": "located",
            "materialStatus": "confirmed",
        },
        {
            "id": f"{prefix}-ev-media",
            "label": "视频片段",
            "locator": {
                "kind": "media",
                "materialId": f"{prefix}-media",
                "materialVersionId": f"{prefix}-media-v1",
                "startSeconds": 1,
                "endSeconds": 2,
            },
            "locationStatus": "located",
            "materialStatus": "confirmed",
        },
        {
            "id": f"{prefix}-ev-scene",
            "label": "场景点",
            "locator": {
                "kind": "scene",
                "materialId": f"{prefix}-scene",
                "materialVersionId": f"{prefix}-scene-v1",
                "pointIds": ["point-1"],
            },
            "locationStatus": "located",
            "materialStatus": "confirmed",
        },
        {
            "id": f"{prefix}-ev-pending",
            "label": "待补材料",
            "locator": None,
            "locationStatus": "pending",
            "materialStatus": "review",
        },
        {
            "id": f"{prefix}-ev-unverifiable",
            "label": "无法核验材料",
            "locator": None,
            "locationStatus": "unverifiable",
            "materialStatus": "conflict",
        },
    ]


def _policy(project_id: str, *, pending: bool, result: str) -> dict[str, Any]:
    evidence_id = f"{project_id}-ev-pending" if pending else f"{project_id}-ev-excel"
    target = {
        "evidenceRef": evidence_id,
        "evidenceRefs": [evidence_id],
        "dimensionId": "compliance",
        "reviewTargetId": "company.registration",
        "factVersionId": None if pending else f"{project_id}-fact-v1",
    }
    if pending:
        target["unavailableReason"] = "材料尚未提供"
    return {
        "id": f"{project_id}-policy-1",
        "ruleId": "HG-OWNERSHIP",
        "ruleVersion": "policy-2026.08",
        "title": "权属硬约束",
        "result": result,
        "evidenceTargets": [target],
        "primaryTarget": target,
        "scope": "融资设备",
        "evidenceRequirement": "需核验权属",
        "gateTriggered": result == "block",
        "responsibleParty": "risk",
        "nextAction": "人工核验",
        "explanation": "确定性测试规则结果",
        "evaluatedAt": "2026-08-10T00:00:00+00:00",
        "isSimulated": True,
    }


_SCORING_FACTS: tuple[tuple[str, str, Any], ...] = (
    ("registration_valid", "compliance", True),
    ("identity_consistency", "compliance", 96.0),
    ("litigation_count", "compliance", 0),
    ("prohibited_status", "compliance", False),
    ("supplier_rating", "transaction", "A级"),
    ("brand_rating", "transaction", "A级"),
    ("financing_ratio", "transaction", 0.75),
    ("term_months", "transaction", 12),
    ("repayment", "transaction", "balanced"),
    ("equipment_utilization", "production", 0.88),
    ("output_consistency", "production", 0.90),
    ("electricity_output_match", "production", 0.92),
    ("process_completeness", "production", 0.94),
    ("staff_stability", "production", 0.91),
    ("order_income_coverage", "revenue", 1.04),
    ("invoice_income_ratio", "revenue", 1.0),
    ("collection_invoice_ratio", "revenue", 0.95),
    ("net_margin", "revenue", 0.13),
    ("rent_coverage", "revenue", 2.2),
    ("debt_revenue_ratio", "debt", 0.32),
    ("short_debt_share", "debt", 0.38),
    ("debt_service_coverage", "debt", 1.9),
    ("duplicate_registration", "debt", False),
    ("guarantee_obligation_ratio", "debt", 0.04),
    ("cashflow_revenue_match", "cashflow", 0.96),
    ("operating_counterparty_share", "cashflow", 0.92),
    ("cashflow_anomaly_rate", "cashflow", 0.01),
    ("net_inflow_ratio", "cashflow", 0.12),
    ("collection_cash_match", "cashflow", 0.94),
)


def _scoring_facts(project_id: str) -> list[dict[str, Any]]:
    evidence_id = f"{project_id}-ev-excel"
    return [
        {
            "id": f"{project_id}-fact-{fact_key.replace('_', '-')}-v1",
            "factKey": fact_key,
            "dimensionId": dimension_id,
            "version": 1,
            "label": fact_key,
            "value": value,
            "unit": None,
            "source": "mock_material_extract",
            "evidenceRefs": [evidence_id],
            "createdAt": "2026-08-10T00:00:00+00:00",
            "isSimulated": True,
        }
        for fact_key, dimension_id, value in _SCORING_FACTS
    ]


def _repayment_schedule(project_id: str) -> dict[str, Any]:
    evidence_id = f"{project_id}-ev-excel"
    points = [
        {
            "id": f"{project_id}-rent-{period}",
            "period": period,
            "principal": 100_000.0,
            "interest": float(13 - period) * 500.0,
            "rent": 100_000.0 + float(13 - period) * 500.0,
            "evidenceRefs": [evidence_id],
            "isSimulated": True,
        }
        for period in range(1, 13)
    ]
    return {
        "status": "available",
        "termMonths": 12,
        "amountUnit": "元",
        "points": points,
        "firstPaymentEvidenceRefs": [evidence_id],
        "firstTwelveEvidenceRefs": [evidence_id],
        "totalRentEvidenceRefs": [evidence_id],
        "termEvidenceRefs": [evidence_id],
        "message": "确定性测试还款计划",
        "sourceLabel": "测试生成器",
        "isSimulated": True,
    }


def _frozen_policies(project_id: str) -> list[dict[str, Any]]:
    evidence_id = f"{project_id}-ev-excel"
    specs = (
        ("CMP-H-001", "compliance", "prohibited_status", "禁入主体状态", "主体合规"),
        (
            "TRX-H-001",
            "transaction",
            "financing_ratio",
            "融资金额不得超过项目金额",
            "交易结构",
        ),
        (
            "DEBT-H-001",
            "debt",
            "duplicate_registration",
            "动产登记重复融资核验",
            "负债核验",
        ),
    )
    results: list[dict[str, Any]] = []
    for rule_id, dimension_id, fact_key, title, scope in specs:
        target = {
            "evidenceRef": evidence_id,
            "evidenceRefs": [evidence_id],
            "dimensionId": dimension_id,
            "reviewTargetId": f"rule-{rule_id}",
            "factVersionId": f"{project_id}-fact-{fact_key.replace('_', '-')}-v1",
        }
        results.append(
            {
                "id": f"constraint-{project_id}-{rule_id.lower()}",
                "ruleId": rule_id,
                "ruleVersion": RULE_VERSION,
                "title": title,
                "result": "pass",
                "evidenceTargets": [target],
                "primaryTarget": target,
                "scope": f"{scope}单项目核验",
                "evidenceRequirement": "必须使用同一材料版本的精确 locator；缺件只能转人工复核。",
                "gateTriggered": False,
                "responsibleParty": "joint",
                "nextAction": "保持规则通过状态",
                "explanation": "已核验事实未触发制度阻断。",
                "evaluatedAt": "2026-08-10T00:00:00+00:00",
                "isSimulated": True,
            }
        )
    return results


def make_bundle(
    project_id: str = "project-a",
    *,
    policy_result: str | None = None,
    policy_pending: bool = False,
    recalculable: bool = False,
    frozen_policies: bool = False,
) -> GeneratedProjectBundle:
    dimensions = _dimensions()
    recalculable = recalculable or frozen_policies
    policies = _frozen_policies(project_id) if frozen_policies else []
    if policy_result is not None:
        policies.append(
            _policy(project_id, pending=policy_pending, result=policy_result)
        )
    facts = [
        {
            "id": f"{project_id}-fact-v1",
            "factKey": "company.registration",
            "dimensionId": "compliance",
            "version": 1,
            "label": "登记状态",
            "value": "正常",
            "unit": None,
            "source": "mock_material_extract",
            "evidenceRefs": [f"{project_id}-ev-excel"],
            "createdAt": "2026-08-10T00:00:00+00:00",
            "isSimulated": True,
        }
    ]
    if recalculable:
        facts.extend(_scoring_facts(project_id))
    catalog = {
        "projectId": project_id,
        "projectNo": f"NO-{project_id}",
        "companyName": f"{project_id} 脱敏制造有限公司",
        "companyShortName": f"{project_id} 脱敏制造",
        "region": "华东",
        "industry": "装备制造",
        "durationDays": 5,
        "store": "测试门店",
        "salesperson": "脱敏业务员",
        "amountWan": 100,
        "financingType": "设备融资",
        "materialStatus": "材料齐备",
        "createdAt": "2026-08-10T00:00:00+00:00",
        "timeBucket": "本月",
        "riskLevel": "attention",
        "riskBand": "关注",
        "decisionGrade": "B",
        "dimensions": deepcopy(dimensions),
        "isSimulated": True,
    }
    workbench = {
        "project": {
            "id": project_id,
            "name": f"{project_id} 脱敏设备融资",
            "materialCount": 5,
            "collaborationIssueCount": 0,
            "dataStatus": "simulated",
            "disclaimer": "仅用于确定性本地测试，不代表真实业务事实。",
            "isSimulated": True,
        },
        "riskSummary": {
            "id": f"{project_id}-risk",
            "name": "风险",
            "level": "attention",
            "scoreGrade": "A",
            "decisionGrade": "B",
            "confidence": 80,
            "summary": "确定性规则汇总",
            "evidenceRefs": [f"{project_id}-ev-excel"],
            "hardConstraintResults": deepcopy(policies),
            "keyAnomalies": [],
            "pendingHumanDeterminations": [],
            "isSimulated": True,
        },
        "dimensions": deepcopy(dimensions),
        "dimensionDetails": _dimension_details(),
        "materials": _materials(project_id),
        "evidence": _evidence(project_id),
        "facts": facts,
        "complianceGraph": {
            "nodes": [],
            "relations": [],
            "attachments": [],
            "sourceLabel": "测试生成器",
            "isSimulated": True,
        },
        "financedEquipment": {
            "currency": "CNY",
            "amountUnit": "元",
            "lines": [],
            "transactionStructure": "direct-lease",
            "lessor": "脱敏出租人",
            "termMonths": 12,
            "downPaymentAmount": 0,
            "financingPlanEvidenceRefs": [],
            "projectAmountEvidenceRefs": [],
            "financingRatioEvidenceRefs": [],
            "partyRelationshipEvidenceRefs": [],
            "totalContractEvidenceRefs": [],
            "repaymentSchedule": _repayment_schedule(project_id) if recalculable else {
                "status": "unavailable",
                "termMonths": 12,
                "amountUnit": "元",
                "points": [],
                "firstPaymentEvidenceRefs": [],
                "firstTwelveEvidenceRefs": [],
                "totalRentEvidenceRefs": [],
                "termEvidenceRefs": [],
                "message": "测试未提供还款计划",
                "sourceLabel": "测试生成器",
                "isSimulated": True,
            },
            "sourceLabel": "测试生成器",
            "isSimulated": True,
        },
        "operatingEquipment": [],
        "productionStages": [],
        "productionEnergy": {
            "status": "unavailable",
            "electricityMetric": "usage",
            "electricityUnit": "kWh",
            "outputMetric": "absolute",
            "outputUnit": "件",
            "aggregation": "sum",
            "points": [],
            "message": "测试未提供生产序列",
            "sourceLabel": "测试生成器",
            "isSimulated": True,
        },
        "referenceImages": [],
        "onsiteAssets": [],
        "corrections": [],
        "determinations": [],
        "reviewEvents": [],
        "layout": {
            "navigationWidth": 212,
            "materialWidth": 520,
            "collaborationHeight": 320,
            "navigationCollapsed": False,
            "middleCollapsed": False,
            "materialCollapsed": False,
            "collaborationCollapsed": False,
            "businessCollapsed": False,
            "policyCollapsed": False,
            "riskCollapsed": False,
            "activeDimensionId": "compliance",
        },
    }
    return GeneratedProjectBundle(catalog=catalog, workbench=workbench)


class StaticGenerator:
    def __init__(
        self,
        *bundles: GeneratedProjectBundle,
        identity: str = "test-generator-v1",
        series_response: dict[str, Any] | None = None,
    ) -> None:
        self._bundles = bundles
        self.identity = identity
        self.series_response = series_response

    def seed_bundles(self):
        return self._bundles

    def query_dimension_series(self, request: DimensionSeriesRequest):
        if self.series_response is None:
            return None
        response = deepcopy(self.series_response)
        response["request"] = request.model_dump(by_alias=True, mode="json")
        return response
