from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.contracts.base import ContractModel
from app.contracts.workbench import BUSINESS_MATERIAL_ROOTS, DimensionId


MaterialValueType = Literal["string", "boolean", "integer", "decimal", "date", "ratio", "money"]
MaterialFactProjection = Literal["candidate_only", "rule_input", "context_only"]
P5_ORIGINAL_MATERIAL_COUNT = 56


class MaterialFieldDefinition(ContractModel):
    field_key: str
    label: str
    dimension_id: DimensionId
    value_type: MaterialValueType
    unit: str | None = None
    source_roles: list[str] = Field(min_length=1)
    fact_projection: MaterialFactProjection
    frontend_visibility: Literal["visible", "backend_reserved"]


class MaterialProcessingStage(ContractModel):
    order: int = Field(ge=1, le=6)
    stage: Literal[
        "original_version",
        "parse_candidate",
        "locator_validation",
        "business_rule",
        "human_confirmation",
        "fact_version",
    ]
    authority: Literal["immutable_input", "advisory_only", "validation", "rule_evaluation", "human_gate", "authoritative_fact"]
    description: str


class MaterialFieldSchema(ContractModel):
    project_id: str
    schema_version: Literal["p5-business-material-v1"] = "p5-business-material-v1"
    business_roots: list[str] = Field(default_factory=lambda: list(BUSINESS_MATERIAL_ROOTS))
    fields: list[MaterialFieldDefinition]
    processing_chain: list[MaterialProcessingStage]
    is_simulated: Literal[True] = True
    data_status: Literal["synthetic_demo"] = "synthetic_demo"
    source: Literal["p5_business_material_schema"] = "p5_business_material_schema"
    disclaimer: str = (
        "字段与处理链用于完整脱敏模拟项目；候选及模型输出必须经 locator 校验与人工确认后才可成为 FactVersion。"
    )


_FIELD_ROWS: tuple[tuple[str, str, DimensionId, MaterialValueType, str | None, tuple[str, ...], MaterialFactProjection, Literal["visible", "backend_reserved"]], ...] = (
    ("company.registration_status", "企业登记状态", "compliance", "string", None, ("营业执照", "工商登记核验"), "rule_input", "visible"),
    ("company.unified_social_credit_code", "统一社会信用代码", "compliance", "string", None, ("营业执照",), "candidate_only", "backend_reserved"),
    ("company.legal_representative", "法定代表人", "compliance", "string", None, ("营业执照", "身份证明"), "rule_input", "backend_reserved"),
    ("company.controller_identity_consistency", "实控人与身份一致性", "compliance", "ratio", "%", ("身份证明", "章程与股权"), "rule_input", "visible"),
    ("company.controller_equity_ratio", "实控人持股比例", "compliance", "ratio", "%", ("章程与股权",), "rule_input", "backend_reserved"),
    ("operation.factory_lease_monthly_rent", "厂房月租金", "production", "money", "万元", ("厂房租赁合同",), "rule_input", "backend_reserved"),
    ("operation.electricity_usage", "用电量", "production", "decimal", "kWh", ("电费",), "rule_input", "visible"),
    ("operation.payroll_amount", "工资总额", "production", "money", "万元", ("工资记录", "银行流水"), "rule_input", "visible"),
    ("operation.staff_count", "在岗人数", "production", "integer", "人", ("工资记录", "生产记录"), "rule_input", "backend_reserved"),
    ("operation.output_quantity", "完工产量", "production", "decimal", "件", ("生产记录", "工单记录"), "rule_input", "visible"),
    ("revenue.sales_invoice_amount", "销项发票金额", "revenue", "money", "万元", ("销项发票",), "rule_input", "visible"),
    ("revenue.purchase_invoice_amount", "进项发票金额", "revenue", "money", "万元", ("进项发票",), "rule_input", "backend_reserved"),
    ("revenue.tax_declared_income", "纳税申报收入", "revenue", "money", "万元", ("纳税申报表",), "rule_input", "visible"),
    ("revenue.financial_statement_revenue", "财务报表营业收入", "revenue", "money", "万元", ("利润表",), "rule_input", "backend_reserved"),
    ("revenue.balance_sheet_assets", "资产总额", "revenue", "money", "万元", ("资产负债表",), "rule_input", "backend_reserved"),
    ("revenue.upstream_concentration", "上游集中度", "revenue", "ratio", "%", ("进项发票", "主要上下游"), "rule_input", "backend_reserved"),
    ("revenue.downstream_concentration", "下游集中度", "revenue", "ratio", "%", ("销项发票", "主要上下游"), "rule_input", "backend_reserved"),
    ("debt.enterprise_credit_balance", "企业征信负债余额", "debt", "money", "万元", ("企业征信",), "rule_input", "visible"),
    ("debt.personal_credit_balance", "个人征信负债余额", "debt", "money", "万元", ("个人征信",), "rule_input", "backend_reserved"),
    ("debt.guarantee_obligation", "对外担保义务", "debt", "money", "万元", ("企业征信", "担保清单"), "rule_input", "visible"),
    ("debt.collateral_asset_value", "增信资产价值", "debt", "money", "万元", ("房产证明", "资产证明"), "rule_input", "backend_reserved"),
    ("cashflow.inflow", "银行流水流入", "cashflow", "money", "万元", ("银行流水",), "rule_input", "visible"),
    ("cashflow.outflow", "银行流水流出", "cashflow", "money", "万元", ("银行流水",), "rule_input", "visible"),
    ("cashflow.counterparty_name", "交易对手方", "cashflow", "string", None, ("银行流水", "主要上下游"), "context_only", "backend_reserved"),
    ("equipment.contract_total", "设备合同总额", "transaction", "money", "万元", ("设备买卖合同",), "rule_input", "visible"),
    ("equipment.quote_total", "设备报价总额", "transaction", "money", "万元", ("设备报价",), "rule_input", "backend_reserved"),
    ("equipment.invoice_total", "设备发票总额", "transaction", "money", "万元", ("设备发票",), "rule_input", "backend_reserved"),
    ("equipment.payment_total", "设备付款总额", "transaction", "money", "万元", ("付款凭证", "银行流水"), "rule_input", "backend_reserved"),
    ("equipment.delivery_status", "设备交付验收状态", "transaction", "string", None, ("交付验收单",), "rule_input", "visible"),
    ("equipment.nameplate_model", "设备铭牌型号", "transaction", "string", None, ("设备铭牌",), "rule_input", "visible"),
)


def build_material_field_schema(project_id: str) -> MaterialFieldSchema:
    fields = [
        MaterialFieldDefinition(
            field_key=field_key,
            label=label,
            dimension_id=dimension_id,
            value_type=value_type,
            unit=unit,
            source_roles=list(source_roles),
            fact_projection=fact_projection,
            frontend_visibility=frontend_visibility,
        )
        for field_key, label, dimension_id, value_type, unit, source_roles, fact_projection, frontend_visibility in _FIELD_ROWS
    ]
    chain_rows = (
        (1, "original_version", "immutable_input", "原件以项目、SHA-256、版本和业务目录路径保存，不因解析结果而改写。"),
        (2, "parse_candidate", "advisory_only", "解析或模型仅生成 Observation 与 ExtractedFieldCandidate。"),
        (3, "locator_validation", "validation", "候选必须校验材料版本及 Excel/PDF/图片/视频 locator。"),
        (4, "business_rule", "rule_evaluation", "规则只读取已验证候选或既有 FactVersion，并保持评分、置信度和 hard gate 分离。"),
        (5, "human_confirmation", "human_gate", "人工明确确认候选或提交业务修正，模型不得越过该 Gate。"),
        (6, "fact_version", "authoritative_fact", "服务端追加不可变 FactVersion，并投影制度、审查链和审批状态。"),
    )
    return MaterialFieldSchema(
        project_id=project_id,
        fields=fields,
        processing_chain=[
            MaterialProcessingStage(order=order, stage=stage, authority=authority, description=description)
            for order, stage, authority, description in chain_rows
        ],
    )


__all__ = [
    "MaterialFieldDefinition",
    "MaterialFieldSchema",
    "MaterialProcessingStage",
    "P5_ORIGINAL_MATERIAL_COUNT",
    "build_material_field_schema",
]
