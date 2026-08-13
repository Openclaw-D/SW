from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import random
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from app.domain.constants import (
    DIMENSION_FULL_NAMES,
    DIMENSION_NAMES,
    DISCLAIMER,
    GENERATOR_VERSION,
    RISK_BAND_LABELS,
    RULE_VERSION,
    SOURCE_LABEL,
)
from app.domain.evidence import (
    build_evidence_targets,
    build_selection_group,
    collect_evidence_refs,
    validate_locators,
)
from app.domain.repayment import (
    build_repayment_points,
    classify_repayment_structure,
    repayment_structure_label,
)
from app.domain.scoring import HARD_GATE_FACT_KEYS, ProjectAssessment, evaluate_project
from app.domain.time_series import aggregate_dimension_series
from app.fixtures.customers import CUSTOMER_TOKENS, SALESPEOPLE, STORES, SUPPLIERS
from app.fixtures.equipment_configurations import build_equipment_configuration
from app.fixtures.industries import INDUSTRIES, EquipmentFixture, IndustryFixture

from .materials import EvidenceRegistry


DEFAULT_GENERATOR_SEED = 20260810
DEFAULT_PROJECT_COUNT = 24
_PATTERNS = ("support", "attention", "confirm", "risk", "forbid")
_TZ = timezone(timedelta(hours=8))
_BASE_TIME = datetime(2026, 8, 1, 9, 0, tzinfo=_TZ)

P5_MATERIAL_COVERAGE: dict[str, tuple[str, ...]] = {
    "compliance": (
        "business-license", "identity-front", "identity-back", "authorization",
        "articles-equity", "registry-litigation",
    ),
    "transaction": (
        "lease-contract", "purchase-contract", "quote", "equipment-invoices", "payment-proof",
        "delivery-acceptance", "equipment-list", "nameplate",
    ),
    "production": (
        "factory-lease", "electricity-bills", "payroll", "operations", "work-orders",
        "equipment-line", "raw-material", "process", "finished-product", "site",
        "site-overhead", "site-front", "site-left", "site-right", "site-rear",
        "equipment-front", "equipment-side", "equipment-rear",
    ),
    "revenue": (
        "order-contracts", "output-invoices", "input-invoices", "tax-return",
        "revenue-ledger", "collections", "balance-sheet", "income-statement",
        "counterparties-summary",
    ),
    "debt": (
        "enterprise-credit", "personal-credit", "encumbrance", "guarantees",
        "maturity-schedule", "collateral-assets", "property-summary", "property-detail",
    ),
    "cashflow": ("bank-statement", "account-info", "counterparties", "operating-match"),
}


_BUSINESS_PATHS: dict[str, tuple[str, str]] = {
    "base-data": ("经营证明/系统导出", "项目全量字段.xlsx"),
    "base-registry": ("基本证照/工商核验", "主体与登记核验.pdf"),
    "base-equipment-image": ("现场照片/设备照片", "设备总览.png"),
    "business-license": ("基本证照", "营业执照.png"),
    "identity-front": ("基本证照/身份证明", "法定代表人身份证正面.png"),
    "identity-back": ("基本证照/身份证明", "法定代表人身份证背面.png"),
    "authorization": ("基本证照/身份证明", "持证授权确认.png"),
    "articles-equity": ("基本证照/股权资料", "公司章程及股权结构.pdf"),
    "registry-litigation": ("基本证照/工商核验", "工商及涉诉核验.pdf"),
    "lease-contract": ("租赁标的/融资租赁", "融资租赁合同.pdf"),
    "purchase-contract": ("租赁标的/设备合同", "设备买卖合同.pdf"),
    "quote": ("租赁标的/设备报价", "设备报价单.pdf"),
    "equipment-invoices": ("租赁标的/设备发票", "设备采购发票.xlsx"),
    "payment-proof": ("租赁标的/付款凭证", "设备付款凭证.xlsx"),
    "delivery-acceptance": ("租赁标的/交付验收", "设备交付验收单.pdf"),
    "equipment-list": ("租赁标的/设备清单", "设备清单.xlsx"),
    "nameplate": ("租赁标的/设备铭牌", "设备铭牌.png"),
    "factory-lease": ("经营证明/厂房租赁合同", "厂房租赁合同.pdf"),
    "electricity-bills": ("经营证明/电费", "电费及用电明细.xlsx"),
    "payroll": ("经营证明/工资", "工资发放明细.xlsx"),
    "operations": ("经营证明/生产经营", "生产记录.xlsx"),
    "work-orders": ("经营证明/生产经营", "工单记录.xlsx"),
    "equipment-line": ("现场照片/设备照片", "产线总览.png"),
    "raw-material": ("现场照片/工艺照片", "原材料.png"),
    "process": ("现场照片/工艺照片", "工艺过程.png"),
    "finished-product": ("现场照片/工艺照片", "成品.png"),
    "site": ("现场照片/厂区照片", "厂区总览.png"),
    "site-overhead": ("现场照片/厂区照片", "厂区俯视图.png"),
    "site-front": ("现场照片/厂区照片", "厂区正面平视图.png"),
    "site-left": ("现场照片/厂区照片", "厂区左侧平视图.png"),
    "site-right": ("现场照片/厂区照片", "厂区右侧平视图.png"),
    "site-rear": ("现场照片/厂区照片", "厂区背面平视图.png"),
    "equipment-front": ("现场照片/设备照片", "设备正视图.png"),
    "equipment-side": ("现场照片/设备照片", "设备侧视图.png"),
    "equipment-rear": ("现场照片/设备照片", "设备背视图.png"),
    "order-contracts": ("经营证明/销售合同", "销售合同.pdf"),
    "output-invoices": ("经营证明/开票资料", "销项发票.xlsx"),
    "input-invoices": ("经营证明/开票资料", "进项发票.xlsx"),
    "tax-return": ("经营证明/纳税申报表", "纳税申报表.xlsx"),
    "revenue-ledger": ("经营证明/财务报表", "收入台账.xlsx"),
    "collections": ("经营证明/回款资料", "回款台账.xlsx"),
    "balance-sheet": ("经营证明/财务报表", "资产负债表.xlsx"),
    "income-statement": ("经营证明/财务报表", "利润表.xlsx"),
    "counterparties-summary": ("经营证明/开票资料", "主要上下游.xlsx"),
    "enterprise-credit": ("增信/企业征信", "企业征信报告.pdf"),
    "personal-credit": ("增信/个人征信", "个人征信报告.pdf"),
    "encumbrance": ("增信/权利负担", "权利负担核验.pdf"),
    "guarantees": ("增信/担保资料", "担保清单.pdf"),
    "maturity-schedule": ("增信/征信明细", "负债到期计划.xlsx"),
    "collateral-assets": ("增信/资产证明", "增信资产清单.xlsx"),
    "property-summary": ("增信/资产证明", "房产信息截图.png"),
    "property-detail": ("增信/资产证明", "房产明细截图.png"),
    "bank-statement": ("增信/流水信息", "银行流水.xlsx"),
    "account-info": ("增信/流水信息", "账户信息.pdf"),
    "counterparties": ("增信/流水信息", "流水主要对手方.xlsx"),
    "operating-match": ("增信/流水信息", "经营流水匹配.xlsx"),
}


def _business_path(category: str) -> dict[str, str]:
    folder_path, file_name = _BUSINESS_PATHS[category]
    return {
        "fileName": file_name,
        "folderPath": folder_path,
        "businessPath": f"{folder_path}/{file_name}",
    }


@dataclass(frozen=True, slots=True)
class GeneratedProjectBundle:
    catalog: dict[str, Any]
    workbench: dict[str, Any]
    dimension_series: tuple[dict[str, Any], ...]
    selection_groups: tuple[dict[str, Any], ...]
    generation: dict[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "catalog": self.catalog,
            "workbench": self.workbench,
            "dimensionSeries": list(self.dimension_series),
            "selectionGroups": list(self.selection_groups),
            "generation": self.generation,
        }


@dataclass(frozen=True, slots=True)
class _Context:
    seed: int
    index: int
    pattern: str
    project_id: str
    project_no: str
    company_name: str
    company_short_name: str
    created_at: str
    industry: IndustryFixture
    equipment: EquipmentFixture
    region: str
    store: str
    salesperson: str
    supplier: str


def _rng(*parts: object) -> random.Random:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _token(*parts: object, length: int = 10) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _context(seed: int, index: int, profile: str = "standard") -> _Context:
    if index < 0:
        raise ValueError("project index cannot be negative")
    industry_index = 0 if profile == "standard" else (index // 4) % len(INDUSTRIES)
    variant = 0 if profile == "standard" else index % 4
    industry = INDUSTRIES[industry_index]
    equipment = industry.equipments[(variant + abs(seed)) % len(industry.equipments)]
    # The public profile intentionally shares one complete, de-identified fact
    # template.  IDs, snapshots and all persisted state remain project-scoped.
    # The old varied profile remains an explicit local opt-in for demonstrations.
    pattern = "confirm" if profile == "standard" else _PATTERNS[(industry_index + variant) % len(_PATTERNS)]
    token = _token("compare-workbench", seed, index, industry.id, equipment.model)
    short_name = f"系统生成·{industry.short_name}{CUSTOMER_TOKENS[index % len(CUSTOMER_TOKENS)]}"
    created = _BASE_TIME - timedelta(days=3 * index + abs(seed) % 7)
    return _Context(
        seed=seed,
        index=index,
        pattern=pattern,
        project_id=f"gen-{industry.id}-{token}",
        project_no=f"SYN-{industry_index + 1:02d}-{index + 1:03d}-{token[:4].upper()}",
        company_name=f"{short_name}有限公司",
        company_short_name=short_name,
        created_at=created.isoformat(),
        industry=industry,
        equipment=equipment,
        region=industry.regions[(variant + seed) % len(industry.regions)],
        store=STORES[(index + seed) % len(STORES)],
        salesperson=SALESPEOPLE[(index * 3 + seed) % len(SALESPEOPLE)],
        supplier=SUPPLIERS[(index + seed) % len(SUPPLIERS)],
    )


def _pattern_inputs(ctx: _Context) -> dict[str, Any]:
    rng = _rng("facts", ctx.seed, ctx.index, ctx.pattern, ctx.industry.id)
    base: dict[str, dict[str, Any]] = {
        "support": {
            "registration_valid": True, "identity_consistency": (95, 100), "litigation_count": 0,
            "supplier_rating": "A级", "brand_rating": "A级", "financing_ratio": (0.66, 0.76), "term_months": 36, "repayment": "front_loaded",
            "equipment_utilization": (0.84, 0.94), "output_consistency": (0.90, 0.98), "electricity_output_match": (0.90, 0.98), "process_completeness": (0.94, 1.0), "staff_stability": (0.90, 0.98),
            "order_income_coverage": (1.05, 1.18), "invoice_income_ratio": (0.96, 1.03), "collection_invoice_ratio": (0.94, 1.02), "net_margin": (0.13, 0.18), "rent_coverage": (2.2, 3.4),
            "debt_revenue_ratio": (0.22, 0.40), "short_debt_share": (0.30, 0.48), "debt_service_coverage": (1.7, 2.3), "duplicate_registration": False, "guarantee_obligation_ratio": (0.02, 0.08),
            "cashflow_revenue_match": (0.92, 1.0), "operating_counterparty_share": (0.88, 0.96), "cashflow_anomaly_rate": (0.001, 0.006), "net_inflow_ratio": (0.10, 0.16), "collection_cash_match": (0.92, 1.0),
        },
        "attention": {
            "registration_valid": True, "identity_consistency": (84, 93), "litigation_count": 1,
            "supplier_rating": "B级", "brand_rating": "B级", "financing_ratio": (0.82, 0.90), "term_months": 48, "repayment": "balanced",
            "equipment_utilization": (0.66, 0.78), "output_consistency": (0.72, 0.84), "electricity_output_match": (0.70, 0.84), "process_completeness": (0.76, 0.88), "staff_stability": (0.72, 0.86),
            "order_income_coverage": (0.88, 1.02), "invoice_income_ratio": (0.82, 0.92), "collection_invoice_ratio": (0.78, 0.90), "net_margin": (0.08, 0.12), "rent_coverage": (1.35, 1.75),
            "debt_revenue_ratio": (0.55, 0.76), "short_debt_share": (0.56, 0.72), "debt_service_coverage": (1.15, 1.55), "duplicate_registration": False, "guarantee_obligation_ratio": (0.10, 0.20),
            "cashflow_revenue_match": (0.76, 0.88), "operating_counterparty_share": (0.72, 0.84), "cashflow_anomaly_rate": (0.012, 0.026), "net_inflow_ratio": (0.04, 0.09), "collection_cash_match": (0.76, 0.90),
        },
        "confirm": {
            "registration_valid": True, "identity_consistency": (86, 95), "litigation_count": 0,
            "supplier_rating": "B级", "brand_rating": "C级", "financing_ratio": (0.76, 0.86), "term_months": 48, "repayment": "balanced",
            "equipment_utilization": (0.70, 0.82), "output_consistency": (0.78, 0.88), "electricity_output_match": (0.78, 0.89), "process_completeness": (0.80, 0.92), "staff_stability": (0.78, 0.90),
            "order_income_coverage": (0.92, 1.04), "invoice_income_ratio": (0.90, 1.08), "collection_invoice_ratio": (0.84, 0.94), "net_margin": (0.09, 0.14), "rent_coverage": (1.5, 2.0),
            "debt_revenue_ratio": (0.44, 0.68), "short_debt_share": (0.46, 0.66), "debt_service_coverage": (1.25, 1.7), "duplicate_registration": False, "guarantee_obligation_ratio": (0.08, 0.16),
            "cashflow_revenue_match": (0.82, 0.92), "operating_counterparty_share": (0.78, 0.90), "cashflow_anomaly_rate": (0.008, 0.020), "net_inflow_ratio": (0.05, 0.11), "collection_cash_match": (0.82, 0.94),
        },
        "risk": {
            "registration_valid": False, "identity_consistency": (58, 72), "litigation_count": 4,
            "supplier_rating": "D级", "brand_rating": "D级", "financing_ratio": (0.94, 0.99), "term_months": 60, "repayment": "back_loaded",
            "equipment_utilization": (0.24, 0.38), "output_consistency": (0.28, 0.42), "electricity_output_match": (0.24, 0.40), "process_completeness": (0.30, 0.44), "staff_stability": (0.34, 0.48),
            "order_income_coverage": (0.44, 0.62), "invoice_income_ratio": (1.35, 1.55), "collection_invoice_ratio": (0.34, 0.52), "net_margin": (0.01, 0.04), "rent_coverage": (0.38, 0.68),
            "debt_revenue_ratio": (1.08, 1.35), "short_debt_share": (0.78, 0.92), "debt_service_coverage": (0.42, 0.72), "duplicate_registration": False, "guarantee_obligation_ratio": (0.32, 0.48),
            "cashflow_revenue_match": (0.40, 0.58), "operating_counterparty_share": (0.42, 0.60), "cashflow_anomaly_rate": (0.07, 0.11), "net_inflow_ratio": (-0.04, 0.01), "collection_cash_match": (0.38, 0.58),
        },
        "forbid": {
            "registration_valid": True, "identity_consistency": (76, 90), "litigation_count": 1,
            "supplier_rating": "C级", "brand_rating": "D级", "financing_ratio": (0.82, 0.94), "term_months": 48, "repayment": "back_loaded",
            "equipment_utilization": (0.58, 0.72), "output_consistency": (0.62, 0.78), "electricity_output_match": (0.58, 0.76), "process_completeness": (0.64, 0.80), "staff_stability": (0.62, 0.80),
            "order_income_coverage": (0.72, 0.90), "invoice_income_ratio": (0.78, 1.20), "collection_invoice_ratio": (0.66, 0.82), "net_margin": (0.06, 0.10), "rent_coverage": (0.95, 1.35),
            "debt_revenue_ratio": (0.72, 0.96), "short_debt_share": (0.62, 0.82), "debt_service_coverage": (0.85, 1.15), "duplicate_registration": True, "guarantee_obligation_ratio": (0.18, 0.30),
            "cashflow_revenue_match": (0.66, 0.80), "operating_counterparty_share": (0.62, 0.76), "cashflow_anomaly_rate": (0.025, 0.050), "net_inflow_ratio": (0.01, 0.06), "collection_cash_match": (0.64, 0.80),
        },
    }[ctx.pattern]
    facts: dict[str, Any] = {}
    for key, value in base.items():
        if isinstance(value, tuple):
            facts[key] = round(rng.uniform(float(value[0]), float(value[1])), 4)
        else:
            facts[key] = value
    facts["prohibited_status"] = ctx.pattern == "forbid"
    facts["term_months"] = int(facts["term_months"])
    return facts


def _evidence_statuses(pattern: str) -> dict[str, str]:
    statuses = {
        "compliance.registration": "verified",
        "compliance.identity": "verified",
        "compliance.prohibited_status": "verified",
        "transaction.financing_ratio": "verified",
        "transaction.ratings": "verified",
        "transaction.repayment": "verified",
        "production.equipment": "verified",
        "production.energy_output": "verified",
        "production.process": "verified",
        "revenue.orders": "verified",
        "revenue.invoice": "verified",
        "revenue.collection": "verified",
        "debt.credit": "verified",
        "debt.duplicate_registration": "verified",
        "debt.obligations": "verified",
        "cashflow.authenticity": "verified",
        "cashflow.operating_match": "verified",
        "cashflow.anomalies": "verified",
    }
    if pattern == "confirm":
        statuses["debt.duplicate_registration"] = "missing"
        statuses["cashflow.anomalies"] = "needs_review"
    return statuses


def _project_amount_wan(ctx: _Context) -> float:
    rng = _rng("amount", ctx.seed, ctx.index, ctx.equipment.model)
    ranges = {
        "metal_processing": (320, 620),
        "plastic_processing": (260, 540),
        "textile": (220, 480),
        "printing_packaging": (420, 760),
        "electronics_manufacturing": (380, 740),
        "glass_processing": (480, 820),
    }
    low, high = ranges[ctx.industry.id]
    return round(rng.uniform(low, high), 2)


def _daily_rows(ctx: _Context, facts: Mapping[str, Any], amount_wan: float) -> dict[str, list[dict[str, Any]]]:
    rng = _rng("daily", ctx.seed, ctx.index, ctx.pattern)
    start = date(2025, 12, 15)
    day_count = 75
    annual_revenue = amount_wan * (2.4 + float(facts["order_income_coverage"]) * 1.8)
    base_income = annual_revenue / 250
    production: list[dict[str, Any]] = []
    revenue: list[dict[str, Any]] = []
    debt: list[dict[str, Any]] = []
    cashflow: list[dict[str, Any]] = []
    base_output = 760 + (ctx.index % 5) * 90
    base_electricity = 1400 + (ctx.index % 4) * 180
    total_debt = annual_revenue * float(facts["debt_revenue_ratio"])
    for offset in range(day_count):
        current = start + timedelta(days=offset)
        business_factor = 0.42 if current.weekday() == 6 else 0.68 if current.weekday() == 5 else 1.0
        utilization = max(0.05, min(0.99, float(facts["equipment_utilization"]) * business_factor + rng.uniform(-0.025, 0.025)))
        output = round(base_output * utilization * (0.94 + rng.random() * 0.12))
        electricity = round(base_electricity * business_factor * (0.94 + rng.random() * 0.12))
        staff = max(8, round(72 * float(facts["staff_stability"]) + rng.uniform(-2, 2)))
        production.append({
            "date": current.isoformat(), "electricity": electricity, "output": output,
            "payroll": round(staff * 0.034, 2), "staff": staff, "utilization": round(utilization * 100, 1),
        })
        order = max(0.0, base_income * float(facts["order_income_coverage"]) * business_factor * rng.uniform(0.90, 1.10))
        income = max(0.0, base_income * business_factor * rng.uniform(0.90, 1.10))
        invoice = income * float(facts["invoice_income_ratio"]) * rng.uniform(0.96, 1.04)
        collection = invoice * float(facts["collection_invoice_ratio"]) * rng.uniform(0.96, 1.04)
        revenue.append({
            "date": current.isoformat(), "orders": round(order, 2), "invoices": round(invoice, 2),
            "collections": round(collection, 2), "income": round(income, 2),
        })
        enterprise = total_debt * 0.74 * (1 - offset / day_count * 0.04)
        personal = total_debt * 0.26 * (1 - offset / day_count * 0.02)
        due = total_debt / 365 * (1.4 if current.day in {10, 20, 28} else 0.25)
        capacity = due * float(facts["debt_service_coverage"])
        debt.append({
            "date": current.isoformat(), "enterprise": round(enterprise, 2), "personal": round(personal, 2),
            "due": round(due, 2), "capacity": round(capacity, 2),
        })
        inflow = collection / max(float(facts["collection_cash_match"]), 0.1)
        net_ratio = float(facts["net_inflow_ratio"])
        outflow = max(0.0, inflow * (1 - net_ratio))
        anomaly = 1 if rng.random() < float(facts["cashflow_anomaly_rate"]) * 4 else 0
        cashflow.append({
            "date": current.isoformat(), "inflow": round(inflow, 2), "outflow": round(outflow, 2),
            "net": round(inflow - outflow, 2), "anomalyCount": anomaly,
        })
    return {"production": production, "revenue": revenue, "debt": debt, "cashflow": cashflow}


def _materials(
    ctx: _Context,
    rows: Mapping[str, list[dict[str, Any]]],
    *,
    project_amount_wan: float,
    financed_amount_wan: float,
    financing_ratio: float,
    down_payment_wan: float,
    facts: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], EvidenceRegistry]:
    excel_id = f"mat-{ctx.project_id}-data"
    excel_version = f"{excel_id}-v1"
    pdf_id = f"mat-{ctx.project_id}-registry"
    pdf_version = f"{pdf_id}-v1"
    image_id = f"mat-{ctx.project_id}-equipment-image"
    image_version = f"{image_id}-v1"
    sheets = [
        {
            "name": "项目摘要",
            "columns": ["项目编号", "客户", "行业", "项目金额(万元)", "融资成数", "融资金额(万元)", "首付款(万元)", "数据状态"],
            "rows": [[ctx.project_no, ctx.company_name, ctx.industry.name, project_amount_wan, round(financing_ratio * 100, 2), financed_amount_wan, down_payment_wan, "业务规则生成"]],
        },
        {
            "name": "合规核验",
            "columns": ["核验项", "结果", "数值", "证据状态", "数据状态"],
            "rows": [
                ["营业登记", "有效" if facts["registration_valid"] else "异常", None, "已定位", "业务规则生成"],
                ["身份一致性", "核验", facts["identity_consistency"], "已定位", "业务规则生成"],
                ["涉诉数量", "核验", facts["litigation_count"], "已定位", "业务规则生成"],
                ["禁入状态", "命中" if facts["prohibited_status"] else "未命中", None, "已定位", "业务规则生成"],
            ],
        },
        {
            "name": "交易设备",
            "columns": ["设备", "品牌", "型号", "数量", "合同单价(万元/台)", "供应商", "供应商评级", "品牌评级", "数据状态"],
            "rows": [[ctx.equipment.equipment, ctx.equipment.brand, ctx.equipment.model, 2, round(project_amount_wan / 2, 2), ctx.supplier, facts["supplier_rating"], facts["brand_rating"], "业务规则生成"]],
        },
        {
            "name": "生产日数据",
            "columns": ["日期", "用电量(kWh)", "完工产量(件)", "工资总额(万元)", "在岗人数(人)", "设备利用率(%)", "数据状态"],
            "rows": [[item["date"], item["electricity"], item["output"], item["payroll"], item["staff"], item["utilization"], "业务规则生成"] for item in rows["production"]],
        },
        {
            "name": "营收日数据",
            "columns": ["日期", "合同订单(万元)", "发票(万元)", "回款流水(万元)", "确认收入(万元)", "数据状态"],
            "rows": [[item["date"], item["orders"], item["invoices"], item["collections"], item["income"], "业务规则生成"] for item in rows["revenue"]],
        },
        {
            "name": "负债日数据",
            "columns": ["日期", "企业负债(万元)", "个人负债(万元)", "到期负债(万元)", "可偿还能力(万元)", "数据状态"],
            "rows": [[item["date"], item["enterprise"], item["personal"], item["due"], item["capacity"], "业务规则生成"] for item in rows["debt"]],
        },
        {
            "name": "流水日数据",
            "columns": ["日期", "流入(万元)", "流出(万元)", "净额(万元)", "异常笔数", "数据状态"],
            "rows": [[item["date"], item["inflow"], item["outflow"], item["net"], item["anomalyCount"], "业务规则生成"] for item in rows["cashflow"]],
        },
    ]
    materials: list[dict[str, Any]] = [
        {
            "id": excel_id,
            "versionId": excel_version,
            **_business_path("base-data"),
            "label": "项目全量字段导入（完整脱敏模拟）",
            "availability": "available",
            "isSimulated": True,
            "sourceLabel": SOURCE_LABEL,
            "kind": "excel",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "sheets": sheets,
        },
        {
            "id": pdf_id,
            "versionId": pdf_version,
            **_business_path("base-registry"),
            "label": "主体与登记核验导入件（完整脱敏模拟）",
            "availability": "available",
            "isSimulated": True,
            "sourceLabel": SOURCE_LABEL,
            "kind": "pdf",
            "mimeType": "application/pdf",
            "pageCount": 3,
            "pages": [
                {"page": 1, "title": "主体状态", "lines": [ctx.company_name, "禁入状态：" + ("命中" if facts["prohibited_status"] else "未命中"), "全部内容为完整脱敏模拟导入"]},
                {"page": 2, "title": "动产登记", "lines": ["重复登记：" + ("存在" if facts["duplicate_registration"] else "未见"), "人工应回到统一登记公示系统核验"]},
                {"page": 3, "title": "担保与其他义务", "lines": [f"对外担保义务比例：{float(facts['guarantee_obligation_ratio']) * 100:.1f}%", "非真实征信或登记报告"]},
            ],
        },
        {
            "id": image_id,
            "versionId": image_version,
            **_business_path("base-equipment-image"),
            "label": f"{ctx.equipment.equipment}设备总览（本地合成）",
            "availability": "available",
            "isSimulated": True,
            "sourceLabel": "Compare 项目级确定性合成资产；不是客户现场、厂家图片、测绘或真实资产重建",
            "kind": "image",
            "mimeType": "image/png",
            "pixelWidth": 2048,
            "pixelHeight": 1152,
            "description": f"{ctx.equipment.equipment} / {ctx.equipment.model} 的项目级合成总览图，不作为真实客户事实。",
            "focalArea": {"x": 0.18, "y": 0.20, "width": 0.64, "height": 0.58},
        },
    ]
    return materials, EvidenceRegistry(
        project_id=ctx.project_id,
        excel_material_id=excel_id,
        excel_version_id=excel_version,
        pdf_material_id=pdf_id,
        pdf_version_id=pdf_version,
        image_material_id=image_id,
        image_version_id=image_version,
    )


def _extend_p5_material_pack(
    ctx: _Context,
    materials: list[dict[str, Any]],
    registry: EvidenceRegistry,
    rows: Mapping[str, list[dict[str, Any]]],
    schedule: Sequence[dict[str, float | int]],
    *,
    project_amount_wan: float,
    financed_amount_wan: float,
    down_payment_wan: float,
    facts: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Append a complete deterministic material pack without widening Front contracts."""

    contract_no = f"FL-{ctx.project_no}-01"
    purchase_no = f"PO-{ctx.project_no}-01"
    delivery_no = f"DA-{ctx.project_no}-01"
    invoice_numbers = (f"INV-{ctx.project_no}-01", f"INV-{ctx.project_no}-02")
    invoice_amounts = (
        round(project_amount_wan * 0.55, 2),
        round(project_amount_wan - round(project_amount_wan * 0.55, 2), 2),
    )
    account_no = f"SYN{_token('account', ctx.seed, ctx.index, length=16).upper()}"
    contract_date = (date.fromisoformat(ctx.created_at[:10]) - timedelta(days=18)).isoformat()
    delivery_date = (date.fromisoformat(ctx.created_at[:10]) - timedelta(days=6)).isoformat()
    refs: dict[str, list[str]] = {dimension: [] for dimension in P5_MATERIAL_COVERAGE}

    def identity(dimension: str, category: str) -> tuple[str, str, str]:
        key = f"{dimension}-{category}"
        material_id = f"mat-{ctx.project_id}-{key}"
        version_id = f"{material_id}-v1"
        registry.bind(key, material_id, version_id)
        return key, material_id, version_id

    def add_pdf(dimension: str, category: str, label: str, pages: list[dict[str, Any]]) -> None:
        key, material_id, version_id = identity(dimension, category)
        materials.append({
            "id": material_id, "versionId": version_id,
            **_business_path(category), "label": label,
            "availability": "available", "isSimulated": True,
            "sourceLabel": f"{SOURCE_LABEL}；完整脱敏 synthetic fixture，不是真实原件",
            "kind": "pdf", "mimeType": "application/pdf",
            "pageCount": len(pages), "pages": pages,
        })
        refs[dimension].append(registry.pdf(
            f"p5-{key}", label, 1,
            {"x": 0.06, "y": 0.10, "width": 0.88, "height": 0.78},
            text_anchor=pages[0]["lines"][0], material_key=key,
        ))

    def add_excel(dimension: str, category: str, label: str, sheets: list[dict[str, Any]]) -> None:
        key, material_id, version_id = identity(dimension, category)
        materials.append({
            "id": material_id, "versionId": version_id,
            **_business_path(category), "label": label,
            "availability": "available", "isSimulated": True,
            "sourceLabel": f"{SOURCE_LABEL}；完整脱敏 synthetic fixture，不是真实原件",
            "kind": "excel",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "sheets": sheets,
        })
        refs[dimension].append(registry.excel(
            f"p5-{key}", label, sheets[0]["name"],
            f"A4:{chr(64 + min(len(sheets[0]['columns']), 26))}4", material_key=key,
        ))

    def add_image(dimension: str, category: str, label: str, description: str) -> None:
        key, material_id, version_id = identity(dimension, category)
        materials.append({
            "id": material_id, "versionId": version_id,
            **_business_path(category), "label": label,
            "availability": "available", "isSimulated": True,
            "sourceLabel": "Compare 项目级确定性合成资产；每个项目具有唯一文件哈希，不是客户现场、厂商图片或事实原件",
            "kind": "image", "mimeType": "image/png",
            "pixelWidth": 2048, "pixelHeight": 1152, "description": description,
            "focalArea": {"x": 0.08, "y": 0.10, "width": 0.84, "height": 0.80},
        })
        refs[dimension].append(registry.image(
            f"p5-{key}", label,
            {"x": 0.08, "y": 0.10, "width": 0.84, "height": 0.80},
            material_key=key,
        ))

    # Compliance package.
    add_image("compliance", "business-license", "营业执照图（完整脱敏模拟）", f"{ctx.company_name} 的纯虚构演示执照卡面；不对应真实企业登记。")
    add_image("compliance", "identity-front", "身份证正面（完整脱敏模拟）", f"系统生成·实控人{ctx.index + 1:02d} 的虚构证件正面；无真人脸、无真实证件号。")
    add_image("compliance", "identity-back", "身份证背面（完整脱敏模拟）", "纯虚构演示证件背面；不复刻任何真实自然人证件。")
    add_image("compliance", "authorization", "持证授权确认（完整脱敏模拟）", "不含真人脸的授权确认示意；仅表达材料形态与证据定位。")
    add_pdf("compliance", "articles-equity", "章程与股权（完整脱敏模拟）", [{
        "page": 1, "title": "章程/股权", "lines": [ctx.company_name, f"实控人持股：{51 + (ctx.index % 4) * 8}%", "其他股权：余额", "已与主体关系图一致"],
    }])
    add_pdf("compliance", "registry-litigation", "工商与涉诉核验（完整脱敏模拟）", [{
        "page": 1, "title": "工商/涉诉", "lines": [ctx.company_name, f"登记状态：{'有效' if facts['registration_valid'] else '异常'}", f"涉诉记录：{facts['litigation_count']}项", f"禁入状态：{'命中' if facts['prohibited_status'] else '未命中'}"],
    }])

    # Transaction package.
    common_contract = [ctx.company_name, f"合同号：{contract_no}", f"设备：{ctx.equipment.brand} {ctx.equipment.model}", "数量：2台", f"总额：{project_amount_wan:.2f}万元", f"签署日：{contract_date}"]
    add_pdf("transaction", "lease-contract", "融资租赁合同（完整脱敏模拟）", [
        {"page": 1, "title": "融资租赁合同", "lines": common_contract + [f"融资金额：{financed_amount_wan:.2f}万元", f"首付款：{down_payment_wan:.2f}万元", f"期数：{len(schedule)}"]},
        *[
            {
                "page": page_index + 2,
                "title": f"租金计划附件（{page_index * 12 + 1}–{min((page_index + 1) * 12, len(schedule))}期）",
                "lines": [
                    f"第{int(point['period'])}期｜本金{float(point['principal']):.2f}元｜利息{float(point['interest']):.2f}元｜租金{float(point['rent']):.2f}元"
                    for point in schedule[page_index * 12 : (page_index + 1) * 12]
                ],
            }
            for page_index in range((len(schedule) + 11) // 12)
        ],
    ])
    add_pdf("transaction", "purchase-contract", "买卖合同（完整脱敏模拟）", [{"page": 1, "title": "买卖合同", "lines": [ctx.company_name, f"合同号：{purchase_no}", f"关联租赁合同：{contract_no}", f"供应商：{ctx.supplier}", f"设备：{ctx.equipment.model}", "数量：2台", f"总额：{project_amount_wan:.2f}万元"]}])
    add_pdf("transaction", "quote", "供应商报价（完整脱敏模拟）", [{"page": 1, "title": "报价", "lines": [ctx.supplier, f"报价关联：{purchase_no}", f"设备：{ctx.equipment.model}", "数量：2台", f"含税总价：{project_amount_wan:.2f}万元", "价格锚点为业务规则生成，不是市场统计"]}])
    add_excel("transaction", "equipment-invoices", "设备采购发票（完整脱敏模拟）", [{
        "name": "设备发票", "columns": ["项目编号", "租赁合同", "采购合同", "发票号", "金额(万元)", "开票日期", "数据状态"],
        "rows": [[ctx.project_no, contract_no, purchase_no, number, amount, delivery_date, "synthetic"] for number, amount in zip(invoice_numbers, invoice_amounts)],
    }])
    add_excel("transaction", "payment-proof", "设备付款凭证（完整脱敏模拟）", [{
        "name": "付款凭证", "columns": ["项目编号", "采购合同", "付款批次", "金额(万元)", "收款方", "付款日期", "状态"],
        "rows": [[ctx.project_no, purchase_no, f"PAY-{index + 1:02d}", amount, ctx.supplier, delivery_date, "已支付-模拟"] for index, amount in enumerate(invoice_amounts)],
    }])
    add_pdf("transaction", "delivery-acceptance", "交付验收（完整脱敏模拟）", [{"page": 1, "title": "交付验收", "lines": [ctx.company_name, f"验收单号：{delivery_no}", f"合同号：{contract_no}", f"设备：{ctx.equipment.model}", "数量：2台", f"验收日：{delivery_date}", "状态：完整验收"]}])
    add_excel("transaction", "equipment-list", "设备清单（完整脱敏模拟）", [{
        "name": "设备清单", "columns": ["项目编号", "合同号", "设备", "品牌", "型号", "数量", "单价(万元)", "合价(万元)", "验收单号"],
        # Keep the unrounded unit price so the workbook formula ``数量*单价``
        # reconciles exactly to odd-cent project totals such as 550.03 万元.
        "rows": [[ctx.project_no, contract_no, ctx.equipment.equipment, ctx.equipment.brand, ctx.equipment.model, 2, project_amount_wan / 2, project_amount_wan, delivery_no]],
    }])
    add_image("transaction", "nameplate", "设备铭牌（本地合成）", f"项目 {ctx.project_no} 的 {ctx.equipment.model} 铭牌结构化示意；不是客户设备照片。")

    # Production originals. SceneSpec/GLB/OCR/locator outputs are deliberately
    # absent here: they are backend-derived artifacts, never raw materials.
    add_pdf("production", "factory-lease", "厂房租赁合同（完整脱敏模拟）", [{
        "page": 1, "title": "厂房租赁合同", "lines": [ctx.company_name, f"厂址：{ctx.region}系统生成工业园", f"月租金：{round(project_amount_wan * 0.012, 2)}万元", "租期：36个月", "用途：生产经营", "数据状态：synthetic/de-identified"],
    }])
    add_excel("production", "electricity-bills", "电费及用电明细（完整脱敏模拟）", [{
        "name": "电费", "columns": ["日期", "项目编号", "户号", "用电量(kWh)", "电费(万元)", "状态"],
        "rows": [[item["date"], ctx.project_no, f"SYN-ELEC-{ctx.index + 1:03d}", item["electricity"], round(float(item["electricity"]) * 0.000078, 4), "已缴-模拟"] for item in rows["production"]],
    }])
    add_excel("production", "payroll", "工资发放明细（完整脱敏模拟）", [{
        "name": "工资", "columns": ["日期", "项目编号", "在岗人数", "工资总额(万元)", "付款账户", "状态"],
        "rows": [[item["date"], ctx.project_no, item["staff"], item["payroll"], account_no, "已发放-模拟"] for item in rows["production"]],
    }])
    add_image("production", "equipment-line", "设备与产线（本地合成）", f"{ctx.equipment.model} 与产线布局示意，仅供演示。")
    add_image("production", "raw-material", "原材料（本地合成）", f"{ctx.equipment.material} 批次示意，仅供演示。")
    add_image("production", "process", "工艺过程（本地合成）", f"{ctx.equipment.process} 工艺示意，仅供演示。")
    add_image("production", "finished-product", "成品（本地合成）", f"{ctx.equipment.product} 成品示意，仅供演示。")
    add_excel("production", "operations", "用电/产量/人员记录（完整脱敏模拟）", [{
        "name": "生产记录", "columns": ["日期", "项目编号", "设备型号", "用电量(kWh)", "产量(件)", "在岗人数", "利用率(%)"],
        "rows": [[item["date"], ctx.project_no, ctx.equipment.model, item["electricity"], item["output"], item["staff"], item["utilization"]] for item in rows["production"]],
    }])
    add_excel("production", "work-orders", "工单记录（完整脱敏模拟）", [{
        "name": "工单", "columns": ["工单号", "日期", "项目编号", "设备型号", "工艺", "完工数量", "状态"],
        "rows": [[f"WO-{ctx.index + 1:02d}-{i + 1:03d}", item["date"], ctx.project_no, ctx.equipment.model, ctx.equipment.process, item["output"], "已完工"] for i, item in enumerate(rows["production"])],
    }])
    add_image("production", "site", "工厂现场（本地合成）", f"项目 {ctx.project_no} 工厂区域布局示意；不是客户现场。")
    for category, label in (
        ("site-overhead", "厂区俯视图（本地合成）"),
        ("site-front", "厂区正面平视图（本地合成）"),
        ("site-left", "厂区左侧平视图（本地合成）"),
        ("site-right", "厂区右侧平视图（本地合成）"),
        ("site-rear", "厂区背面平视图（本地合成）"),
        ("equipment-front", "设备正视图（本地合成）"),
        ("equipment-side", "设备侧视图（本地合成）"),
        ("equipment-rear", "设备背视图（本地合成）"),
    ):
        add_image("production", category, label, f"项目 {ctx.project_no} 的受控脱敏模拟视角；不是客户现场拍摄。")

    revenue_total = round(sum(float(item["income"]) for item in rows["revenue"]), 2)
    collection_total = round(sum(float(item["collections"]) for item in rows["revenue"]), 2)
    invoice_total = round(sum(float(item["invoices"]) for item in rows["revenue"]), 2)
    input_invoice_total = round(invoice_total * (0.56 + (ctx.index % 4) * 0.03), 2)
    debt_total = round(float(rows["debt"][-1]["enterprise"]) + float(rows["debt"][-1]["personal"]), 2)
    total_assets = round(max(debt_total * 1.45, project_amount_wan * 1.8), 2)
    total_equity = round(total_assets - debt_total, 2)
    period_profit = round(revenue_total * float(facts["net_margin"]), 2)
    add_pdf("revenue", "order-contracts", "订单与销售合同（完整脱敏模拟）", [{"page": 1, "title": "订单/合同", "lines": [ctx.company_name, f"项目编号：{ctx.project_no}", f"观察期订单：{sum(float(item['orders']) for item in rows['revenue']):.2f}万元", f"观察期确认收入：{revenue_total:.2f}万元", f"期间：{rows['revenue'][0]['date']}至{rows['revenue'][-1]['date']}"]}])
    add_excel("revenue", "output-invoices", "销项发票（完整脱敏模拟）", [{"name": "销项发票", "columns": ["日期", "项目编号", "发票金额(万元)", "确认收入(万元)", "数据状态"], "rows": [[item["date"], ctx.project_no, item["invoices"], item["income"], "synthetic"] for item in rows["revenue"]]}])
    add_excel("revenue", "input-invoices", "进项发票（完整脱敏模拟）", [{"name": "进项发票", "columns": ["日期", "项目编号", "供应方", "发票金额(万元)", "税额(万元)", "数据状态"], "rows": [[item["date"], ctx.project_no, f"系统生成·供应方{(index % 4) + 1}", round(float(item["invoices"]) * input_invoice_total / max(invoice_total, 0.01), 2), round(float(item["invoices"]) * input_invoice_total / max(invoice_total, 0.01) * 0.13, 2), "synthetic"] for index, item in enumerate(rows["revenue"])]}])
    add_excel("revenue", "tax-return", "纳税申报与税表（完整脱敏模拟）", [{"name": "税表", "columns": ["期间", "项目编号", "计税收入(万元)", "销项税额(万元)", "申报状态"], "rows": [["2025-12至2026-02", ctx.project_no, invoice_total, round(invoice_total * 0.13, 2), "已申报-模拟"]]}])
    add_excel("revenue", "revenue-ledger", "收入台账（完整脱敏模拟）", [{"name": "收入台账", "columns": ["日期", "项目编号", "合同订单(万元)", "确认收入(万元)", "累计收入(万元)", "数据状态"], "rows": [[item["date"], ctx.project_no, item["orders"], item["income"], round(sum(float(row["income"]) for row in rows["revenue"][:i + 1]), 2), "synthetic"] for i, item in enumerate(rows["revenue"])]}])
    add_excel("revenue", "collections", "回款台账（完整脱敏模拟）", [{"name": "回款", "columns": ["日期", "项目编号", "账户", "回款金额(万元)", "累计回款(万元)"], "rows": [[item["date"], ctx.project_no, account_no, item["collections"], round(sum(float(row["collections"]) for row in rows["revenue"][:i + 1]), 2)] for i, item in enumerate(rows["revenue"])]}])
    add_excel("revenue", "balance-sheet", "资产负债表（完整脱敏模拟）", [{"name": "资产负债表", "columns": ["期间", "项目编号", "资产总额(万元)", "负债总额(万元)", "所有者权益(万元)", "勾稽状态"], "rows": [["观察期末", ctx.project_no, total_assets, debt_total, total_equity, "资产=负债+权益"]]}])
    add_excel("revenue", "income-statement", "利润表（完整脱敏模拟）", [{"name": "利润表", "columns": ["期间", "项目编号", "营业收入(万元)", "营业成本及费用(万元)", "净利润(万元)", "勾稽状态"], "rows": [["观察期", ctx.project_no, revenue_total, round(revenue_total - period_profit, 2), period_profit, "收入-成本费用=净利润"]]}])
    add_excel("revenue", "counterparties-summary", "主要上下游（完整脱敏模拟）", [{"name": "主要上下游", "columns": ["项目编号", "方向", "对手方", "观察期金额(万元)", "份额(%)", "来源"], "rows": [[ctx.project_no, "下游", f"系统生成·客户{index}", round(invoice_total * share / 100, 2), share, "销项发票"] for index, share in enumerate((38, 27, 21, 14), start=1)] + [[ctx.project_no, "上游", f"系统生成·供应方{index}", round(input_invoice_total * share / 100, 2), share, "进项发票"] for index, share in enumerate((41, 26, 19, 14), start=1)]}])

    add_pdf("debt", "enterprise-credit", "企业征信报告（完整脱敏模拟）", [{"page": 1, "title": "企业征信", "lines": [ctx.company_name, f"项目编号：{ctx.project_no}", f"企业负债余额：{float(rows['debt'][-1]['enterprise']):.2f}万元", f"短期负债占比：{float(facts['short_debt_share']) * 100:.2f}%", "非真实人民银行征信报告"]}])
    add_pdf("debt", "personal-credit", "个人征信报告（完整脱敏模拟）", [{"page": 1, "title": "个人征信", "lines": [f"系统生成·实控人{ctx.index + 1:02d}", f"关联项目：{ctx.project_no}", f"个人负债余额：{float(rows['debt'][-1]['personal']):.2f}万元", "身份与报告均为完整脱敏模拟", "非真实个人征信报告"]}])
    add_pdf("debt", "encumbrance", "权利负担核验（完整脱敏模拟）", [{"page": 1, "title": "中登/权利负担", "lines": [ctx.company_name, f"设备型号：{ctx.equipment.model}", f"重复登记：{'存在' if facts['duplicate_registration'] else '未见'}", f"关联合同：{contract_no}", "需由人工回到正式登记系统复核"]}])
    add_pdf("debt", "guarantees", "担保清单（完整脱敏模拟）", [{"page": 1, "title": "担保", "lines": [ctx.company_name, f"担保义务比例：{float(facts['guarantee_obligation_ratio']) * 100:.2f}%", f"负债基数：{debt_total:.2f}万元", f"担保义务：{debt_total * float(facts['guarantee_obligation_ratio']):.2f}万元"]}])
    add_excel("debt", "maturity-schedule", "到期计划（完整脱敏模拟）", [{"name": "到期计划", "columns": ["日期", "项目编号", "企业负债(万元)", "个人负债(万元)", "期末负债(万元)", "当日到期(万元)", "偿付能力(万元)"], "rows": [[item["date"], ctx.project_no, item["enterprise"], item["personal"], round(float(item["enterprise"]) + float(item["personal"]), 2), item["due"], item["capacity"]] for item in rows["debt"]]}])
    add_excel("debt", "collateral-assets", "增信资产清单（完整脱敏模拟）", [{"name": "资产清单", "columns": ["项目编号", "资产类型", "权属标识", "评估价值(万元)", "权利状态", "数据状态"], "rows": [[ctx.project_no, "工业房产", f"SYN-PROP-{ctx.index + 1:03d}", round(project_amount_wan * 0.72, 2), "待人工核验", "synthetic"]]}])
    add_image("debt", "property-summary", "房产信息截图（本地合成）", f"项目 {ctx.project_no} 的脱敏房产信息界面示意，不是真实不动产页面。")
    add_image("debt", "property-detail", "房产明细截图（本地合成）", f"项目 {ctx.project_no} 的脱敏房产明细示意，不是真实权属证明。")

    add_excel("cashflow", "bank-statement", "完整期间银行流水（完整脱敏模拟）", [{"name": "银行流水", "columns": ["日期", "账户", "项目编号", "主要对手方", "流入(万元)", "流出(万元)", "净额(万元)", "异常笔数"], "rows": [[item["date"], account_no, ctx.project_no, f"系统生成·对手方{(i % 4) + 1}", item["inflow"], item["outflow"], item["net"], item["anomalyCount"]] for i, item in enumerate(rows["cashflow"])]}])
    add_pdf("cashflow", "account-info", "账户信息（完整脱敏模拟）", [{"page": 1, "title": "账户信息", "lines": [ctx.company_name, f"账户：{account_no}", f"开户标识：SYN-BANK-{ctx.index + 1:02d}", f"期间：{rows['cashflow'][0]['date']}至{rows['cashflow'][-1]['date']}", "非真实银行账户"]}])
    add_excel("cashflow", "counterparties", "主要对手方（完整脱敏模拟）", [{"name": "对手方", "columns": ["账户", "项目编号", "对手方", "属性", "观察期份额(%)"], "rows": [[account_no, ctx.project_no, f"系统生成·对手方{i}", "经营", share] for i, share in enumerate((36, 28, 21, 15), start=1)]}])
    add_excel("cashflow", "operating-match", "经营匹配（完整脱敏模拟）", [{"name": "经营匹配", "columns": ["项目编号", "账户", "观察期收入(万元)", "观察期回款(万元)", "流水流入(万元)", "回款流水匹配", "数据状态"], "rows": [[ctx.project_no, account_no, revenue_total, collection_total, round(sum(float(item["inflow"]) for item in rows["cashflow"]), 2), facts["collection_cash_match"], "synthetic"]]}])
    return refs


def _dimension_series(
    registry: EvidenceRegistry,
    rows: Mapping[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], ...]:
    definitions: dict[str, list[tuple[str, str, str, str, str, str, str]]] = {
        "production": [
            ("electricity", "用电量", "kWh", "sum", "production-electricity-bills", "电费", "D"),
            ("output", "完工产量", "件", "sum", "production-operations", "生产记录", "E"),
            ("payroll", "工资总额", "万元", "sum", "production-payroll", "工资", "D"),
            ("staff", "在岗人数", "人", "last", "production-operations", "生产记录", "F"),
            ("utilization", "设备利用率", "%", "average", "production-operations", "生产记录", "G"),
        ],
        "revenue": [
            ("orders", "合同订单", "万元", "sum", "revenue-revenue-ledger", "收入台账", "C"),
            ("invoices", "发票", "万元", "sum", "revenue-output-invoices", "销项发票", "C"),
            ("collections", "回款流水", "万元", "sum", "revenue-collections", "回款", "D"),
            ("income", "确认收入", "万元", "sum", "revenue-revenue-ledger", "收入台账", "D"),
        ],
        "debt": [
            ("enterprise", "企业负债", "万元", "last", "debt-maturity-schedule", "到期计划", "C"),
            ("personal", "个人负债", "万元", "last", "debt-maturity-schedule", "到期计划", "D"),
            ("due", "到期负债", "万元", "sum", "debt-maturity-schedule", "到期计划", "F"),
            ("capacity", "可偿还能力", "万元", "last", "debt-maturity-schedule", "到期计划", "G"),
        ],
        "cashflow": [
            ("inflow", "流入", "万元", "sum", "cashflow-bank-statement", "银行流水", "E"),
            ("outflow", "流出", "万元", "sum", "cashflow-bank-statement", "银行流水", "F"),
            ("net", "净额", "万元", "sum", "cashflow-bank-statement", "银行流水", "G"),
        ],
    }
    series: list[dict[str, Any]] = []
    for dimension_id in ("production", "revenue", "debt", "cashflow"):
        metrics = definitions[dimension_id]
        observations: list[dict[str, Any]] = []
        for row_index, row in enumerate(rows[dimension_id], start=4):
            for metric_id, label, unit, aggregation, material_key, sheet, column in metrics:
                evidence_ref = registry.excel(
                    f"ts-{dimension_id}-{row['date']}-{metric_id}",
                    f"{row['date']} {label}",
                    sheet,
                    f"{column}{row_index}:{column}{row_index}",
                    material_key=material_key,
                )
                observations.append({
                    "id": f"{dimension_id}-{row['date']}-{metric_id}",
                    "date": row["date"],
                    "metricId": metric_id,
                    "value": float(row[metric_id]),
                    "evidenceRefs": [evidence_ref],
                    "isSimulated": True,
                })
        series.append({
            "dimensionId": dimension_id,
            "supportedGrains": ["day", "week", "month", "year"],
            "metrics": [{"id": metric_id, "label": label, "unit": unit, "aggregation": aggregation} for metric_id, label, unit, aggregation, *_ in metrics],
            "observations": observations,
            "sourceLabel": SOURCE_LABEL,
            "isSimulated": True,
        })
    return tuple(series)


def _aggregate(
    series: Mapping[str, Any],
    project_id: str,
    grain: str = "month",
) -> list[dict[str, Any]]:
    request = {
        "projectId": project_id,
        "dimensionId": series["dimensionId"],
        "metricIds": [metric["id"] for metric in series["metrics"]],
        "grain": grain,
        "startDate": min(item["date"] for item in series["observations"]),
        "endDate": max(item["date"] for item in series["observations"]),
        "timezone": "Asia/Shanghai",
    }
    response = aggregate_dimension_series(series, request)
    if response["status"] != "available":
        raise RuntimeError(response.get("message", "time-series aggregation failed"))
    return list(response["points"])


_FACT_DEFINITIONS: dict[str, tuple[str, str, str | None, str]] = {
    "registration_valid": ("compliance", "营业登记有效", None, "compliance.registration"),
    "identity_consistency": ("compliance", "主体身份一致性", "%", "compliance.identity"),
    "litigation_count": ("compliance", "涉诉记录数量", "项", "compliance.identity"),
    "prohibited_status": ("compliance", "禁入主体状态", None, "compliance.prohibited_status"),
    "supplier_rating": ("transaction", "供应商评级", None, "transaction.ratings"),
    "brand_rating": ("transaction", "品牌评级", None, "transaction.ratings"),
    "financing_ratio": ("transaction", "融资成数", None, "transaction.financing_ratio"),
    "term_months": ("transaction", "融资期限", "月", "transaction.repayment"),
    "repayment": ("transaction", "还款结构", None, "transaction.repayment"),
    "equipment_utilization": ("production", "设备利用率", None, "production.equipment"),
    "output_consistency": ("production", "产量连续性", None, "production.energy_output"),
    "electricity_output_match": ("production", "用电产量匹配度", None, "production.energy_output"),
    "process_completeness": ("production", "工艺记录完整度", None, "production.process"),
    "staff_stability": ("production", "在岗人员稳定度", None, "production.process"),
    "order_income_coverage": ("revenue", "订单收入覆盖", None, "revenue.orders"),
    "invoice_income_ratio": ("revenue", "开票收入比", None, "revenue.invoice"),
    "collection_invoice_ratio": ("revenue", "回款开票比", None, "revenue.collection"),
    "net_margin": ("revenue", "净利率", None, "revenue.collection"),
    "rent_coverage": ("revenue", "租金覆盖倍数", "倍", "revenue.collection"),
    "debt_revenue_ratio": ("debt", "负债营收比", None, "debt.credit"),
    "short_debt_share": ("debt", "短期负债占比", None, "debt.credit"),
    "debt_service_coverage": ("debt", "偿债覆盖倍数", "倍", "debt.obligations"),
    "duplicate_registration": ("debt", "重复融资登记", None, "debt.duplicate_registration"),
    "guarantee_obligation_ratio": ("debt", "担保义务占比", None, "debt.obligations"),
    "cashflow_revenue_match": ("cashflow", "流水营收匹配度", None, "cashflow.authenticity"),
    "operating_counterparty_share": ("cashflow", "经营对手方占比", None, "cashflow.operating_match"),
    "cashflow_anomaly_rate": ("cashflow", "异常流水比例", None, "cashflow.anomalies"),
    "net_inflow_ratio": ("cashflow", "净流入比例", None, "cashflow.authenticity"),
    "collection_cash_match": ("cashflow", "回款流水匹配度", None, "cashflow.operating_match"),
}


def _fact_identifier(project_id: str, key: str) -> str:
    return f"fact-{project_id}-{key.replace('.', '-').replace('_', '-')}-v1"


def _fact_versions(
    ctx: _Context,
    facts: Mapping[str, Any],
    derived_entries: Sequence[tuple[str, str, str, Any, str | None, str]],
    evidence_statuses: Mapping[str, str],
    materials: list[dict[str, Any]],
    registry: EvidenceRegistry,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    entries: list[tuple[str, str, str, Any, str | None, str]] = [
        (key, dimension_id, label, facts[key], unit, status_key)
        for key, (dimension_id, label, unit, status_key) in _FACT_DEFINITIONS.items()
    ]
    entries.extend(derived_entries)
    versions: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for key, dimension_id, label, value, unit, status_key in entries:
        status = evidence_statuses.get(status_key, "verified")
        if status == "missing":
            evidence_ref = registry.pending(
                f"fact-{key.replace('.', '-')}",
                f"{label}待补材料，尚无可解析 locator",
            )
            evidence_refs = [evidence_ref]
        else:
            # Source originals are attached after every business pack has been
            # built. Never manufacture a "rule facts" worksheet and call it an
            # original merely to give a derived FactVersion a locator.
            evidence_refs = []
        if key == "registration_valid":
            evidence_refs.append(
                registry.pdf(
                    "base-registry-import",
                    "主体登记系统导入核验件",
                    1,
                    {"x": 0.08, "y": 0.12, "width": 0.84, "height": 0.30},
                    text_anchor=ctx.company_name,
                )
            )
        elif key == "project_amount_wan":
            evidence_refs.append(
                registry.excel("project-summary-amount", "项目金额摘要", "项目摘要", "D4:D4")
            )
        fact_id = _fact_identifier(ctx.project_id, key)
        item = {
            "id": fact_id,
            "factKey": f"{dimension_id}.{key}",
            "dimensionId": dimension_id,
            "version": 1,
            "label": label,
            "value": value,
            "unit": unit,
            "source": "mock_material_extract",
            "evidenceRefs": evidence_refs,
            "createdAt": ctx.created_at,
            "isSimulated": True,
        }
        versions.append(item)
        by_key[key] = item
    return versions, by_key


def _structure_rows(
    ctx: _Context,
    derived: Mapping[str, Any],
) -> list[dict[str, Any]]:
    upstream = (("核心原材料", 44.0), ("设备耗材", 31.0), ("物流能源", 25.0))
    downstream = (("制造客户", 46.0), ("经销渠道", 32.0), ("服务客户", 22.0))
    aging = (("30天内", 57.0), ("31–60天", 27.0), ("60天以上", 16.0))
    rows: list[dict[str, Any]] = []
    for group, values, unit in (
        ("revenue-upstream", upstream, "%"),
        ("revenue-downstream", downstream, "%"),
        ("revenue-receivable-aging", aging, "%"),
    ):
        for index, (label, value) in enumerate(values, start=1):
            rows.append({"id": f"{group}-{index}", "dimension": "revenue", "group": group, "label": label, "value": value, "unit": unit, "note": "确定性结构比例"})
    for item_id, label, value in derived["profit_segments"]:
        rows.append({"id": item_id, "dimension": "revenue", "group": "revenue-profitability", "label": label, "value": value, "unit": "万元", "note": "年度营收减费用后与净利润勾稽"})
    for group, values in (
        ("debt-enterprise-creditors", derived["enterprise_creditors"]),
        ("debt-personal-creditors", derived["personal_creditors"]),
    ):
        for item_id, label, value in values:
            rows.append({"id": item_id, "dimension": "debt", "group": group, "label": label, "value": value, "unit": "万元", "note": "确定性债务拆分"})
    for item_id, label, value, limit, share in derived["exposures"]:
        rows.append({"id": item_id, "dimension": "debt", "group": "debt-project-exposure", "label": label, "value": value, "unit": "W", "note": f"formal-product-channels-v2 · 限额{limit}W · 份额{share}%"})
    for group, total, labels in (
        ("cashflow-inflow-parties", derived["cashflow_in"], ("主要客户A", "主要客户B", "渠道回款", "其他经营流入")),
        ("cashflow-outflow-parties", derived["cashflow_out"], ("核心供应商A", "核心供应商B", "工资税费", "其他经营流出")),
    ):
        shares = (36.0, 28.0, 21.0, 15.0)
        allocated = [round(total * share / 100, 2) for share in shares[:-1]]
        allocated.append(round(total - sum(allocated), 2))
        for index, (label, value, share) in enumerate(zip(labels, allocated, shares), start=1):
            rows.append({"id": f"{group}-{index}", "dimension": "cashflow", "group": group, "label": f"系统生成·{ctx.industry.short_name}{label}", "value": value, "unit": "万元", "note": f"观察期份额{share:.0f}%"})
    return rows


def _structure_evidence_refs(
    registry: EvidenceRegistry,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    source_categories = {
        "revenue-upstream": ("counterparties-summary", "input-invoices"),
        "revenue-downstream": ("counterparties-summary", "output-invoices"),
        "revenue-receivable-aging": ("output-invoices", "collections"),
        "revenue-profitability": ("income-statement", "input-invoices"),
        "debt-enterprise-creditors": ("enterprise-credit",),
        "debt-personal-creditors": ("personal-credit",),
        "debt-project-exposure": ("enterprise-credit", "lease-contract"),
        "cashflow-inflow-parties": ("bank-statement", "counterparties"),
        "cashflow-outflow-parties": ("bank-statement", "counterparties"),
    }
    evidence_by_material = {
        str(item["locator"]["materialId"]): str(item["id"])
        for item in registry.items
        if item.get("locator") is not None
    }
    refs: dict[str, str] = {}
    for row in rows:
        categories = source_categories[str(row["group"])]
        source_ref = next(
            (
                evidence_ref
                for material_id, evidence_ref in evidence_by_material.items()
                if any(material_id.endswith(f"-{category}") for category in categories)
            ),
            None,
        )
        if source_ref is None:
            raise RuntimeError(f"structure row lacks an original source: {row['id']}")
        refs[str(row["id"])] = source_ref
    return refs


def _strip_period(point: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": point["id"],
        "label": point["label"],
        "measures": list(point["measures"]),
        "note": point.get("note"),
    }


def _derived_values(
    ctx: _Context,
    facts: Mapping[str, Any],
    rows: Mapping[str, list[dict[str, Any]]],
    schedule: Sequence[Mapping[str, float | int]],
    project_amount_wan: float,
    financed_amount_wan: float,
) -> dict[str, Any]:
    annual_revenue = round(sum(float(row["income"]) for row in rows["revenue"]) * 365 / len(rows["revenue"]), 2)
    net_profit = round(annual_revenue * float(facts["net_margin"]), 2)
    expense_total = round(annual_revenue - net_profit, 2)
    expense_shares = (0.72, 0.06, 0.07, 0.09)
    expenses = [round(expense_total * share, 2) for share in expense_shares]
    expenses.append(round(expense_total - sum(expenses), 2))
    profit_segments = [
        ("revenue-profit-material", "材料成本", expenses[0]),
        ("revenue-profit-site-rent", "场地房租", expenses[1]),
        ("revenue-profit-utilities", "水电费用", expenses[2]),
        ("revenue-profit-payroll", "人工费用", expenses[3]),
        ("revenue-profit-other", "其他费用", expenses[4]),
        ("revenue-profit-net-profit", "净利润", net_profit),
    ]
    total_debt = round(annual_revenue * float(facts["debt_revenue_ratio"]), 2)
    enterprise_debt = round(total_debt * 0.74, 2)
    personal_debt = round(total_debt - enterprise_debt, 2)

    def allocate(total: float, specs: Sequence[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
        values = [round(total * share, 2) for _, _, share in specs[:-1]]
        values.append(round(total - sum(values), 2))
        return [(item_id, label, value) for (item_id, label, _), value in zip(specs, values)]

    enterprise_creditors = allocate(enterprise_debt, (
        ("debt-enterprise-bank-a", "系统生成·经营银行A", 0.34),
        ("debt-enterprise-bank-b", "系统生成·经营银行B", 0.28),
        ("debt-enterprise-lessor", "系统生成·融资租赁机构", 0.22),
        ("debt-enterprise-other", "其他经营负债", 0.16),
    ))
    personal_creditors = allocate(personal_debt, (
        ("debt-personal-controller", "实控人", 0.46),
        ("debt-personal-spouse", "配偶", 0.24),
        ("debt-personal-shareholder", "其他股东", 0.18),
        ("debt-personal-other", "其他关联自然人", 0.12),
    ))
    current_exposure = round(financed_amount_wan, 2)
    history_exposure = round(min(max(project_amount_wan * 0.18, 18.0), max(0.0, 1000.0 - current_exposure)), 2)
    total_exposure = round(current_exposure + history_exposure, 2)
    shares = (19, 20, 29, 32)
    values = [round(total_exposure * share / 100, 2) for share in shares[:-1]]
    values.append(round(total_exposure - sum(values), 2))
    exposure_specs = (
        ("debt-exposure-direct-200", "200直", 200),
        ("debt-exposure-core-200", "200核心", 200),
        ("debt-exposure-core-300", "300核心", 300),
        ("debt-exposure-core-500", "500核心", 500),
    )
    exposures = [
        (item_id, label, value, limit, share)
        for (item_id, label, limit), value, share in zip(exposure_specs, values, shares)
    ]
    first_twelve_rent_wan = round(sum(float(point["rent"]) for point in schedule[:12]) / 10_000, 4)
    cashflow_in = round(sum(float(row["inflow"]) for row in rows["cashflow"]), 2)
    cashflow_out = round(sum(float(row["outflow"]) for row in rows["cashflow"]), 2)
    return {
        "annual_revenue": annual_revenue,
        "net_profit": net_profit,
        "profit_segments": profit_segments,
        "first_twelve_rent_wan": first_twelve_rent_wan,
        "rent_coverage": round(net_profit / max(first_twelve_rent_wan, 0.0001), 2),
        "total_debt": total_debt,
        "enterprise_debt": enterprise_debt,
        "personal_debt": personal_debt,
        "enterprise_creditors": enterprise_creditors,
        "personal_creditors": personal_creditors,
        "history_exposure": history_exposure,
        "current_exposure": current_exposure,
        "total_exposure": total_exposure,
        "exposures": exposures,
        "cashflow_in": cashflow_in,
        "cashflow_out": cashflow_out,
        "cashflow_net": round(cashflow_in - cashflow_out, 2),
        "cashflow_anomalies": int(sum(int(row["anomalyCount"]) for row in rows["cashflow"])),
    }


def _dimension_definitions(assessment: ProjectAssessment) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "index": index,
            "name": DIMENSION_NAMES[item.id],
            "fullName": DIMENSION_FULL_NAMES[item.id],
            "score": item.score,
            "scoreGrade": item.score_grade,
            "confidence": item.confidence,
            "summary": item.summary,
        }
        for index, item in enumerate(assessment.dimensions, start=1)
    ]


def _tone(score: float) -> str:
    if score >= 80:
        return "positive"
    if score >= 60:
        return "neutral"
    if score >= 40:
        return "attention"
    return "critical"


def _dimension_details(
    ctx: _Context,
    facts: Mapping[str, Any],
    assessment: ProjectAssessment,
    fact_by_key: Mapping[str, Mapping[str, Any]],
    structure_refs: Mapping[str, str],
    dimension_series: Sequence[Mapping[str, Any]],
    schedule: Sequence[Mapping[str, float | int]],
    schedule_refs: Sequence[str],
    derived: Mapping[str, Any],
) -> list[dict[str, Any]]:
    assessment_by_id = {item.id: item for item in assessment.dimensions}
    series_by_id = {item["dimensionId"]: item for item in dimension_series}
    monthly = {dimension_id: [_strip_period(point) for point in _aggregate(series, ctx.project_id)] for dimension_id, series in series_by_id.items()}

    def refs(key: str) -> list[str]:
        return list(fact_by_key[key]["evidenceRefs"])

    def metric(item_id: str, label: str, value: str, note: str, key: str, score: float | None = None) -> dict[str, Any]:
        return {"id": item_id, "label": label, "value": value, "note": note, "tone": _tone(score if score is not None else assessment_by_id[fact_by_key[key]["dimensionId"]].score), "evidenceRefs": refs(key)}

    def breakdown(item_id: str, label: str, value: str, detail: str, key: str) -> dict[str, Any]:
        return {"id": item_id, "label": label, "value": value, "detail": detail, "tone": _tone(assessment_by_id[fact_by_key[key]["dimensionId"]].score), "evidenceRefs": refs(key)}

    def segment(item_id: str, label: str, value: float, unit: str, tone: str = "neutral", note: str | None = None) -> dict[str, Any]:
        return {"id": item_id, "label": label, "value": value, "unit": unit, "note": note, "tone": tone, "evidenceRefs": [structure_refs[item_id]]}

    production_points = monthly["production"]
    payroll_points: list[dict[str, Any]] = []
    for point in production_points:
        measures = {measure["label"]: measure for measure in point["measures"]}
        payroll = measures.get("工资总额")
        staff = measures.get("在岗人数")
        if payroll is None or staff is None:
            continue
        payroll_points.append({
            # The frozen Front treats ids beginning with `timeseries-` as
            # authoritative temporal data and derives summary evidence from
            # the actual measures instead of legacy single-project mock ids.
            "id": f"timeseries-production-payroll-{point['id']}",
            "label": point["label"],
            "note": "工资总额、期末在岗人数及其确定性派生人均值",
            "measures": [
                payroll,
                staff,
                {"id": f"{point['id']}-per-capita", "label": "人均工资", "value": round(float(payroll["value"]) / max(float(staff["value"]), 1), 2), "unit": "万元/人/月", "evidenceRefs": list(dict.fromkeys([*payroll["evidenceRefs"], *staff["evidenceRefs"]]))},
            ],
        })

    revenue_compositions = []
    for group_id, label in (("revenue-upstream", "上游"), ("revenue-downstream", "下游"), ("revenue-receivable-aging", "应收账龄")):
        group_rows = [key for key in structure_refs if key.startswith(f"{group_id}-")]
        labels = {
            "revenue-upstream": ("核心原材料", "设备耗材", "物流能源"),
            "revenue-downstream": ("制造客户", "经销渠道", "服务客户"),
            "revenue-receivable-aging": ("30天内", "31–60天", "60天以上"),
        }[group_id]
        values = (44.0, 31.0, 25.0) if group_id == "revenue-upstream" else (46.0, 32.0, 22.0) if group_id == "revenue-downstream" else (57.0, 27.0, 16.0)
        revenue_compositions.append({"id": group_id, "label": label, "segments": [segment(item_id, item_label, value, "%", "attention" if index == 2 else "neutral") for index, (item_id, item_label, value) in enumerate(zip(group_rows, labels, values))]})
    revenue_compositions.append({"id": "revenue-profitability", "label": "利润与租金覆盖", "segments": [segment(item_id, label, value, "万元", "positive" if item_id == "revenue-profit-net-profit" else "neutral") for item_id, label, value in derived["profit_segments"]]})

    debt_compositions = [
        {"id": "debt-enterprise-creditors", "label": "企业负债", "segments": [segment(item_id, label, value, "万元") for item_id, label, value in derived["enterprise_creditors"]]},
        {"id": "debt-personal-creditors", "label": "个人负债", "segments": [segment(item_id, label, value, "万元") for item_id, label, value in derived["personal_creditors"]]},
        {"id": "debt-project-exposure", "label": "项目通道敞口", "segments": [segment(item_id, label, value, "W", "attention" if value / limit > 0.85 else "neutral", f"formal-product-channels-v2 · 限额{limit}W · 份额{share}%") for item_id, label, value, limit, share in derived["exposures"]]},
    ]
    return _dimension_detail_payload(
        ctx=ctx,
        facts=facts,
        assessment_by_id=assessment_by_id,
        fact_by_key=fact_by_key,
        refs=refs,
        metric=metric,
        breakdown=breakdown,
        segment=segment,
        structure_refs=structure_refs,
        derived=derived,
        schedule=schedule,
        schedule_refs=schedule_refs,
        production_points=production_points,
        payroll_points=payroll_points,
        revenue_compositions=revenue_compositions,
        debt_compositions=debt_compositions,
        monthly=monthly,
    )


def _constraint_payloads(
    ctx: _Context,
    assessment: ProjectAssessment,
    fact_by_key: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payloads: list[dict[str, Any]] = []
    selection_groups: list[dict[str, Any]] = []
    for item in assessment.constraints:
        fact = fact_by_key[HARD_GATE_FACT_KEYS[item.evidence_key]]
        unavailable_reason = "关键材料尚未补齐，locator 显式 pending" if item.result == "manual_review" else None
        targets = build_evidence_targets(
            evidence_refs=fact["evidenceRefs"],
            dimension_id=item.dimension_id,
            review_target_id=f"rule-{item.rule_id}",
            fact_version_id=fact["id"],
            unavailable_reason=unavailable_reason,
        )
        selection_groups.append(build_selection_group(targets))
        payloads.append(
            {
                "id": f"constraint-{ctx.project_id}-{item.rule_id.lower()}",
                "ruleId": item.rule_id,
                "ruleVersion": RULE_VERSION,
                "title": item.title,
                "result": item.result,
                "evidenceTargets": targets,
                "primaryTarget": targets[0] if targets else None,
                "scope": f"{DIMENSION_FULL_NAMES[item.dimension_id]}单项目核验",
                "evidenceRequirement": "必须使用同一材料版本的精确 locator；缺件只能转人工复核。",
                "gateTriggered": item.result == "block",
                "responsibleParty": "joint",
                "nextAction": "阻断并由人工确认" if item.result == "block" else "补件后人工复核" if item.result == "manual_review" else "保持规则通过状态",
                "explanation": item.explanation,
                "evaluatedAt": ctx.created_at,
                "isSimulated": True,
            }
        )
    return payloads, selection_groups


def _reference_images(ctx: _Context) -> list[dict[str, Any]]:
    categories = (
        ("equipment", ctx.equipment.equipment, "设备参数化占位"),
        ("raw-material", ctx.equipment.material, "原料流程占位"),
        ("process", ctx.equipment.process, "工艺流程占位"),
        ("finished-product", ctx.equipment.product, "成品流程占位"),
    )
    colors = ("6b7f99", "8a817c", "748c78", "8b7e94")
    result: list[dict[str, Any]] = []
    for index, ((category, title, description), color) in enumerate(zip(categories, colors), start=1):
        svg_markup = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='960' height='540'>"
            f"<rect width='960' height='540' fill='#{color}'/>"
            f"<text x='48' y='280' font-size='34' fill='white'>{title}</text></svg>"
        )
        svg = "data:image/svg+xml;charset=utf-8," + quote(svg_markup)
        result.append({
            "id": f"reference-{ctx.project_id}-{category}",
            "category": category,
            "src": svg,
            "title": title,
            "description": f"{description}；仅用于界面布局和行业语义，不是客户现场或厂商照片。",
            "author": "Compare 确定性生成器",
            "originUrl": "",
            "license": "内部模拟占位数据",
            "licenseUrl": "",
            "usage": "非证据、不可用于事实认定",
            "isEvidence": False,
        })
    return result


def _targets_for_fact(
    fact: Mapping[str, Any],
    *,
    review_target_id: str,
    unavailable_reason: str | None = None,
) -> list[dict[str, Any]]:
    return build_evidence_targets(
        evidence_refs=fact["evidenceRefs"],
        dimension_id=fact["dimensionId"],
        review_target_id=review_target_id,
        fact_version_id=fact["id"],
        unavailable_reason=unavailable_reason,
    )


def generate_project_bundle(seed: int, index: int, profile: str = "standard") -> GeneratedProjectBundle:
    """Generate one complete, internally reconciled and deterministic project."""

    ctx = _context(seed, index, profile)
    inputs = _pattern_inputs(ctx)
    statuses = _evidence_statuses(ctx.pattern)
    project_amount_wan = _project_amount_wan(ctx)
    financing_ratio = float(inputs["financing_ratio"])
    financed_amount_wan = round(project_amount_wan * financing_ratio, 2)
    down_payment_wan = round(project_amount_wan - financed_amount_wan, 2)
    schedule = build_repayment_points(
        financed_amount_wan * 10_000,
        int(inputs["term_months"]),
        0.062 + (index % 4) * 0.003,
        str(inputs["repayment"]),  # type: ignore[arg-type]
    )
    configuration = build_equipment_configuration(
        ctx.industry.id,
        ctx.equipment.equipment,
        ctx.equipment.model,
        ctx.project_id,
        seed,
        ctx.pattern,
    )
    rows = _daily_rows(ctx, inputs, project_amount_wan)
    materials, registry = _materials(
        ctx,
        rows,
        project_amount_wan=project_amount_wan,
        financed_amount_wan=financed_amount_wan,
        financing_ratio=financing_ratio,
        down_payment_wan=down_payment_wan,
        facts=inputs,
    )
    pack_refs = _extend_p5_material_pack(
        ctx,
        materials,
        registry,
        rows,
        schedule,
        project_amount_wan=project_amount_wan,
        financed_amount_wan=financed_amount_wan,
        down_payment_wan=down_payment_wan,
        facts=inputs,
    )
    dimension_series = _dimension_series(registry, rows)
    derived = _derived_values(ctx, inputs, rows, schedule, project_amount_wan, financed_amount_wan)
    contract_unit_price = round(project_amount_wan * 10_000 / 2, 2)
    benchmark_low = round(contract_unit_price * 0.88, 2)
    benchmark_median = round(contract_unit_price * 0.96, 2)
    benchmark_high = round(contract_unit_price * 1.08, 2)
    derived_entries = [
        ("project_amount_wan", "transaction", "项目金额", project_amount_wan, "万元", "transaction.financing_ratio"),
        ("financed_amount_wan", "transaction", "融资金额", financed_amount_wan, "万元", "transaction.financing_ratio"),
        ("down_payment_wan", "transaction", "首付款", down_payment_wan, "万元", "transaction.financing_ratio"),
        ("price_benchmark", "transaction", "设备价格规则基准", f"{benchmark_low}/{benchmark_median}/{benchmark_high}/{contract_unit_price}", "元/台", "transaction.ratings"),
        ("annual_revenue", "revenue", "规则年化营收", derived["annual_revenue"], "万元", "revenue.collection"),
        ("net_profit", "revenue", "规则净利润", derived["net_profit"], "万元", "revenue.collection"),
        ("first_twelve_rent_wan", "revenue", "前12期项目租金", derived["first_twelve_rent_wan"], "万元", "transaction.repayment"),
        ("derived_rent_coverage", "revenue", "派生租金覆盖倍数", derived["rent_coverage"], "倍", "revenue.collection"),
        ("total_debt", "debt", "总负债", derived["total_debt"], "万元", "debt.credit"),
        ("history_exposure", "debt", "历史项目敞口", derived["history_exposure"], "W", "debt.credit"),
        ("current_exposure", "debt", "本次项目敞口", derived["current_exposure"], "W", "debt.credit"),
        ("total_exposure", "debt", "项目总敞口", derived["total_exposure"], "W", "debt.credit"),
        ("cashflow_in", "cashflow", "观察期流入", derived["cashflow_in"], "万元", "cashflow.authenticity"),
        ("cashflow_out", "cashflow", "观察期流出", derived["cashflow_out"], "万元", "cashflow.authenticity"),
        ("cashflow_net", "cashflow", "观察期净额", derived["cashflow_net"], "万元", "cashflow.authenticity"),
        ("cashflow_anomalies", "cashflow", "观察期异常笔数", derived["cashflow_anomalies"], "笔", "cashflow.anomalies"),
    ]
    fact_versions, fact_by_key = _fact_versions(ctx, inputs, derived_entries, statuses, materials, registry)
    evidence_by_material = {
        item["locator"]["materialId"]: item["id"]
        for item in registry.items
        if item.get("locator") is not None
    }
    fact_source_categories: dict[str, tuple[str, ...]] = {
        "registration_valid": ("business-license", "registry-litigation"),
        "identity_consistency": ("identity-front", "identity-back", "authorization", "articles-equity"),
        "litigation_count": ("registry-litigation",),
        "prohibited_status": ("registry-litigation",),
        "supplier_rating": ("purchase-contract", "quote"),
        "brand_rating": ("quote", "nameplate"),
        "financing_ratio": ("lease-contract", "purchase-contract"),
        "term_months": ("lease-contract",),
        "repayment": ("lease-contract",),
        "project_amount_wan": ("purchase-contract", "equipment-invoices", "payment-proof"),
        "financed_amount_wan": ("lease-contract",),
        "down_payment_wan": ("lease-contract", "payment-proof"),
        "price_benchmark": ("purchase-contract", "quote"),
        "equipment_utilization": ("equipment-line", "operations"),
        "output_consistency": ("finished-product", "operations", "work-orders"),
        "electricity_output_match": ("electricity-bills", "operations"),
        "process_completeness": ("process", "work-orders"),
        "staff_stability": ("payroll", "operations"),
        "order_income_coverage": ("order-contracts", "revenue-ledger"),
        "invoice_income_ratio": ("output-invoices", "income-statement"),
        "collection_invoice_ratio": ("collections", "output-invoices", "bank-statement"),
        "net_margin": ("income-statement", "tax-return"),
        "rent_coverage": ("income-statement", "lease-contract"),
        "annual_revenue": ("income-statement", "tax-return"),
        "net_profit": ("income-statement",),
        "debt_revenue_ratio": ("enterprise-credit", "personal-credit", "income-statement"),
        "short_debt_share": ("enterprise-credit", "maturity-schedule"),
        "debt_service_coverage": ("maturity-schedule", "bank-statement"),
        "duplicate_registration": ("encumbrance",),
        "guarantee_obligation_ratio": ("enterprise-credit", "guarantees"),
        "total_debt": ("enterprise-credit", "personal-credit", "balance-sheet"),
        "cashflow_revenue_match": ("bank-statement", "income-statement"),
        "operating_counterparty_share": ("counterparties", "counterparties-summary"),
        "cashflow_anomaly_rate": ("bank-statement",),
        "net_inflow_ratio": ("bank-statement",),
        "collection_cash_match": ("bank-statement", "collections"),
        "cashflow_in": ("bank-statement",),
        "cashflow_out": ("bank-statement",),
        "cashflow_net": ("bank-statement",),
        "cashflow_anomalies": ("bank-statement",),
    }
    for fact in fact_versions:
        dimension_pack_refs = pack_refs[str(fact["dimensionId"])]
        fact_key = str(fact["factKey"]).split(".", 1)[1]
        category_refs = [
            evidence_by_material[f"mat-{ctx.project_id}-{fact['dimensionId']}-{category}"]
            for category in fact_source_categories.get(fact_key, ())
            if f"mat-{ctx.project_id}-{fact['dimensionId']}-{category}" in evidence_by_material
        ]
        # Cross-dimension reconciliation (for example bank statement versus
        # income statement) is added explicitly without changing fact ownership.
        for category in fact_source_categories.get(fact_key, ()):
            for dimension_id in P5_MATERIAL_COVERAGE:
                material_id = f"mat-{ctx.project_id}-{dimension_id}-{category}"
                if material_id in evidence_by_material:
                    category_refs.append(evidence_by_material[material_id])
        fact["evidenceRefs"] = list(
            dict.fromkeys([*fact["evidenceRefs"], *category_refs, dimension_pack_refs[0]])
        )

    configuration_refs = [
        evidence_by_material[f"mat-{ctx.project_id}-transaction-{category}"]
        for category in ("quote", "equipment-list", "nameplate")
    ]
    for row in configuration:
        fact_id = _fact_identifier(ctx.project_id, f"configuration-{row['id']}")
        row["factVersionId"] = fact_id
        row["evidenceRefs"] = configuration_refs
        fact_versions.append({
            "id": fact_id,
            "factKey": f"transaction.configuration.{ctx.equipment.model}.{row['id']}",
            "dimensionId": "transaction",
            "version": 1,
            "label": f"{ctx.equipment.model} {row['label']}",
            "value": f"{row['current']} / {row['median']} / {row['range']}",
            "unit": row["unit"],
            "source": "mock_material_extract",
            "evidenceRefs": configuration_refs,
            "createdAt": ctx.created_at,
            "isSimulated": True,
        })

    schedule_refs = [
        registry.pdf(
            f"rent-period-{point['period']}",
            f"第{point['period']}期本金、利息与租金",
            2 + (int(point["period"]) - 1) // 12,
            {
                "x": 0.08,
                "y": 0.08 + ((int(point["period"]) - 1) % 12) * 0.07,
                "width": 0.84,
                "height": 0.055,
            },
            text_anchor=f"第{int(point['period'])}期",
            material_key="transaction-lease-contract",
        )
        for point in schedule
    ]
    structure_data = _structure_rows(ctx, derived)
    structure_refs = _structure_evidence_refs(registry, structure_data)
    assessment = evaluate_project(inputs, statuses, schedule)
    dimensions = _dimension_definitions(assessment)
    details = _dimension_details(
        ctx, inputs, assessment, fact_by_key, structure_refs, dimension_series,
        schedule, schedule_refs, derived,
    )
    hard_constraints, selection_groups = _constraint_payloads(ctx, assessment, fact_by_key)

    identity_targets = _targets_for_fact(
        fact_by_key["identity_consistency"], review_target_id="compliance-identity"
    )
    selection_groups.append(build_selection_group(identity_targets))
    primary_constraint = hard_constraints[-1] if ctx.pattern == "confirm" else hard_constraints[0]
    constraint_targets = list(primary_constraint["evidenceTargets"])
    event_specs = [
        ("fact_version_created", "system", "材料识别层", "compliance", identity_targets, "主体身份多证据已建立原子选择组", [], "resolved"),
        ("policy_result_recorded", "system", "制度规则层", primary_constraint["evidenceTargets"][0]["dimensionId"], constraint_targets, f"{primary_constraint['title']}：{primary_constraint['result']}", [f"{primary_constraint['ruleId']}@{RULE_VERSION}"], "pending_gate" if primary_constraint["result"] != "pass" else "resolved"),
        ("risk_question_submitted", "risk", "风控辅助", "transaction", _targets_for_fact(fact_by_key["financing_ratio"], review_target_id="transaction-financing-ratio"), "请复核融资成数与实际租金计划的勾稽关系", [], "open"),
    ]
    review_events: list[dict[str, Any]] = []
    base_dt = datetime.fromisoformat(ctx.created_at)
    for sequence, (event_type, actor, actor_label, dimension_id, targets, summary, rule_refs, issue_status) in enumerate(event_specs, start=1):
        target_refs: list[str] = []
        target_fact_ids: list[str] = []
        target_review_ids: list[str] = []
        for target in targets:
            target_refs.extend(target.get("evidenceRefs") or [target["evidenceRef"]])
            if target.get("factVersionId"):
                target_fact_ids.append(target["factVersionId"])
            if target.get("reviewTargetId"):
                target_review_ids.append(target["reviewTargetId"])
        unique_review_ids = list(dict.fromkeys(target_review_ids))
        review_events.append({
            "id": f"event-{ctx.project_id}-{sequence}", "projectId": ctx.project_id, "sequence": sequence,
            "threadId": f"thread-{ctx.project_id}-{dimension_id}", "replyToEventId": None,
            "issueStatus": issue_status, "eventType": event_type, "actor": actor, "actorLabel": actor_label,
            "dimensionId": dimension_id, "evidenceTargets": targets,
            "reviewTargetId": unique_review_ids[0] if len(unique_review_ids) == 1 else None,
            "title": summary.split("：", 1)[0], "summary": summary,
            "factVersionIds": list(dict.fromkeys(target_fact_ids)),
            "evidenceRefs": list(dict.fromkeys(target_refs)), "ruleRefs": rule_refs,
            "createdAt": (base_dt + timedelta(minutes=sequence * 5)).isoformat(),
            "immutable": True, "isSimulated": True,
        })

    representative_keys = {
        "compliance": "registration_valid", "transaction": "financing_ratio",
        "production": "equipment_utilization", "revenue": "collection_invoice_ratio",
        "debt": "debt_revenue_ratio", "cashflow": "cashflow_anomaly_rate",
    }
    anomalies: list[dict[str, Any]] = []
    for dimension in sorted(assessment.dimensions, key=lambda item: item.score)[:2]:
        fact = fact_by_key[representative_keys[dimension.id]]
        targets = _targets_for_fact(fact, review_target_id=f"anomaly-{dimension.id}")
        selection_groups.append(build_selection_group(targets))
        anomalies.append({
            "id": f"risk-anomaly-{ctx.project_id}-{dimension.id}", "title": f"{DIMENSION_NAMES[dimension.id]}重点核验",
            "detail": f"该维度规则分 {dimension.score:.1f}，需回到原始材料核验。", "level": assessment.risk_level,
            "evidenceTargets": targets, "primaryTarget": targets[0], "responsibleParty": "joint",
            "nextAction": "按精确 locator 复核事实与规则输入", "isSimulated": True,
        })
    pending_items = []
    for constraint in hard_constraints:
        if constraint["result"] != "manual_review":
            continue
        pending_items.append({
            "id": f"pending-{constraint['id']}", "title": constraint["title"],
            "detail": "材料缺失只降低置信并触发人工复核，不自动拒绝。", "level": "confirm",
            "evidenceTargets": constraint["evidenceTargets"], "primaryTarget": constraint["primaryTarget"],
            "responsibleParty": "joint", "nextAction": "补充可定位材料后重新核验", "isSimulated": True,
        })
    risk_refs = list(dict.fromkeys(ref for item in hard_constraints for ref in collect_evidence_refs(item)))

    determination_payloads = []
    for dimension in assessment.dimensions:
        scoped_constraints = [item for item in hard_constraints if item["evidenceTargets"][0]["dimensionId"] == dimension.id]
        representative = fact_by_key[representative_keys[dimension.id]]
        determination_payloads.append({
            "id": f"determination-{ctx.project_id}-{dimension.id}", "dimensionId": dimension.id,
            "score": dimension.score, "scoreGrade": dimension.score_grade,
            "decisionGrade": "E" if any(item["result"] == "block" for item in scoped_constraints) else dimension.score_grade,
            "confidence": dimension.confidence, "conclusion": dimension.summary,
            "evidenceRefs": list(representative["evidenceRefs"]), "hardConstraintResults": scoped_constraints,
            "softRecommendations": [{
                "id": f"soft-{ctx.project_id}-{dimension.id}", "dimensionId": dimension.id,
                "title": f"{DIMENSION_NAMES[dimension.id]}事实复核", "recommendation": "建议按版本一致的原始材料逐项复核；该建议不改变制度 Gate。",
                "confidence": dimension.confidence, "evidenceRefs": list(representative["evidenceRefs"]),
                "advisoryOnly": True, "isSimulated": True,
            }], "isSimulated": True,
        })

    image_evidence = registry.image(
        "equipment-original-region", "设备总览原件区域",
        {"x": 0.18, "y": 0.20, "width": 0.64, "height": 0.58},
    )
    references: list[dict[str, Any]] = []
    original_ids = {
        category: f"mat-{ctx.project_id}-{dimension}-{category}"
        for dimension, categories in P5_MATERIAL_COVERAGE.items()
        for category in categories
    }
    evidence_by_material = {
        item["locator"]["materialId"]: item["id"]
        for item in registry.items
        if item.get("locator") is not None
    }
    equipment_image_ids = [
        materials[2]["id"],
        original_ids["equipment-line"],
        original_ids["equipment-front"],
        original_ids["equipment-side"],
        original_ids["equipment-rear"],
    ]
    production_monthly = {point["label"]: point for point in _aggregate(next(item for item in dimension_series if item["dimensionId"] == "production"), ctx.project_id)}
    energy_points = []
    for point in production_monthly.values():
        measures = {measure["label"]: measure for measure in point["measures"]}
        energy_points.append({
            "id": f"production-energy-{point['id']}", "date": point["periodStart"], "label": point["label"],
            "electricity": float(measures["用电量"]["value"]), "output": float(measures["完工产量"]["value"]),
            "electricityEvidenceRefs": list(measures["用电量"]["evidenceRefs"]),
            "outputEvidenceRefs": list(measures["完工产量"]["evidenceRefs"]), "isSimulated": True,
        })
    utilization_percent = float(inputs["equipment_utilization"]) * 100
    schedule_points = [
        {"id": f"rent-{ctx.project_id}-{point['period']}", "period": point["period"], "principal": point["principal"], "interest": point["interest"], "rent": point["rent"], "evidenceRefs": [schedule_refs[i]], "isSimulated": True}
        for i, point in enumerate(schedule)
    ]
    model_kinds = ("machining-center", "turning-center", "sliding-head-lathe")
    price_fact = fact_by_key["price_benchmark"]
    workbench = {
        "project": {"id": ctx.project_id, "name": f"{ctx.company_short_name}·{ctx.equipment.equipment}设备融资", "materialCount": len(materials), "collaborationIssueCount": sum(event["issueStatus"] in {"open", "pending_gate"} for event in review_events), "dataStatus": "simulated", "disclaimer": DISCLAIMER, "isSimulated": True},
        "riskSummary": {
            "id": f"risk-{ctx.project_id}", "name": "风险", "level": assessment.risk_level,
            "scoreGrade": assessment.score_grade, "decisionGrade": assessment.decision_grade,
            "confidence": assessment.confidence,
            "summary": f"六维等权规则分 {assessment.overall_score:.1f}；风险为全局五级汇总，制度 Gate 独立判断。",
            "evidenceRefs": risk_refs, "hardConstraintResults": hard_constraints,
            "keyAnomalies": anomalies, "pendingHumanDeterminations": pending_items, "isSimulated": True,
        },
        "dimensions": dimensions, "dimensionDetails": details, "materials": materials,
        "evidence": registry.items, "facts": fact_versions,
        "complianceGraph": {
            "nodes": [
                {"id": f"company-{ctx.project_id}", "kind": "company", "name": ctx.company_name, "role": "承租人", "verificationStatus": "confirmed", "evidenceRefs": list(fact_by_key["registration_valid"]["evidenceRefs"])},
                {"id": f"person-{ctx.project_id}", "kind": "person", "name": f"系统生成·实控人{ctx.index + 1:02d}", "role": "法定代表人/实控人", "verificationStatus": "confirmed", "evidenceRefs": list(fact_by_key["identity_consistency"]["evidenceRefs"])},
            ],
            "relations": [{"id": f"relation-{ctx.project_id}", "fromId": f"person-{ctx.project_id}", "toId": f"company-{ctx.project_id}", "relation": "controller", "sharePercent": round(51 + (ctx.index % 4) * 8.0, 1), "label": "控制关系", "verificationStatus": "confirmed", "evidenceRefs": list(fact_by_key["identity_consistency"]["evidenceRefs"])}],
            "attachments": [{"id": f"attachment-{ctx.project_id}-identity", "subjectId": f"person-{ctx.project_id}", "factVersionId": fact_by_key["identity_consistency"]["id"], "label": "主体身份一致性", "verificationStatus": "confirmed", "evidenceRefs": list(fact_by_key["identity_consistency"]["evidenceRefs"])}],
            "sourceLabel": SOURCE_LABEL, "isSimulated": True,
        },
        "financedEquipment": {
            "currency": "CNY", "amountUnit": "元", "lines": [{
                "id": f"financed-{ctx.project_id}-1", "equipment": ctx.equipment.equipment, "brand": ctx.equipment.brand,
                "model": ctx.equipment.model, "quantity": 2, "contractUnitPrice": contract_unit_price,
                "supplier": ctx.supplier, "contractQuoteSource": "租赁标的/设备合同/设备买卖合同.pdf",
                "supplierQuoteSource": "租赁标的/设备报价/设备报价单.pdf", "imageId": materials[2]["id"],
                "imageIds": equipment_image_ids,
                "nameplateMaterialId": original_ids["nameplate"],
                "derivedModelRef": f"derived-scene:{ctx.project_id}:equipment-v1",
                "modelPreset": {"kind": model_kinds[index % 3], "width": round(2.1 + index % 4 * 0.2, 2), "height": round(1.7 + index % 3 * 0.2, 2), "depth": round(1.6 + index % 5 * 0.15, 2), "spindleCount": 1 + index % 2, "axisCount": 3 + index % 6, "accent": "#7089a5"},
                "priceBenchmark": {"status": "available", "priceBasis": "per_unit", "low": benchmark_low, "median": benchmark_median, "high": benchmark_high, "sampleLabel": "同配置业务规则价格锚点", "message": "仅作单台含税价格核验结构，不是厂商报价或历史统计样本。", "unit": "元/台", "sourceLabel": SOURCE_LABEL, "factVersionId": price_fact["id"], "evidenceRefs": list(price_fact["evidenceRefs"])},
                "configuration": {"status": "available", "message": "按行业、设备名称和型号精确匹配，无跨设备回退。", "rows": configuration},
                "supplierRating": inputs["supplier_rating"], "supplierRatingEvidenceRefs": list(fact_by_key["supplier_rating"]["evidenceRefs"]),
                "brandRating": inputs["brand_rating"], "brandRatingEvidenceRefs": list(fact_by_key["brand_rating"]["evidenceRefs"]),
                "contractEvidenceRefs": list(fact_by_key["project_amount_wan"]["evidenceRefs"]), "supplierQuoteEvidenceRefs": list(price_fact["evidenceRefs"]),
            }],
            "transactionStructure": "direct-lease", "lessor": "系统生成·融资租赁主体", "termMonths": int(inputs["term_months"]),
            "downPaymentAmount": down_payment_wan * 10_000,
            "financingPlanEvidenceRefs": list(dict.fromkeys([*fact_by_key["financed_amount_wan"]["evidenceRefs"], *fact_by_key["term_months"]["evidenceRefs"]])),
            "projectAmountEvidenceRefs": list(fact_by_key["project_amount_wan"]["evidenceRefs"]),
            "financingRatioEvidenceRefs": list(fact_by_key["financing_ratio"]["evidenceRefs"]),
            "partyRelationshipEvidenceRefs": list(fact_by_key["identity_consistency"]["evidenceRefs"]),
            "totalContractEvidenceRefs": list(fact_by_key["project_amount_wan"]["evidenceRefs"]),
            "repaymentSchedule": {"status": "available", "termMonths": len(schedule), "amountUnit": "元", "points": schedule_points, "firstPaymentEvidenceRefs": [schedule_refs[0]], "firstTwelveEvidenceRefs": list(schedule_refs[:12]), "totalRentEvidenceRefs": list(schedule_refs), "termEvidenceRefs": list(fact_by_key["term_months"]["evidenceRefs"]), "message": f"由实际本金与利息计划推导为{repayment_structure_label(schedule)}；排序规则为前高后低最安全、均衡其次、前低后高最危险。", "sourceLabel": SOURCE_LABEL, "isSimulated": True},
            "sourceLabel": SOURCE_LABEL, "isSimulated": True,
        },
        "operatingEquipment": [{"id": f"operating-{ctx.project_id}", "equipment": ctx.equipment.equipment, "model": ctx.equipment.model, "operatingQuantity": 2 + index % 5, "status": "operating" if utilization_percent >= 55 else "idle", "utilization": f"{utilization_percent:.1f}%", "ratedCapacity": f"{round(1800 * (0.7 + index % 5 * 0.08)):,} {ctx.equipment.capacity_unit}", "processUse": ctx.equipment.process, "evidenceRefs": list(fact_by_key["equipment_utilization"]["evidenceRefs"]), "sourceLabel": SOURCE_LABEL, "isSimulated": True}],
        "productionStages": [
            {"id": f"stage-{ctx.project_id}-raw", "stage": "raw-material", "title": f"{ctx.equipment.material}入库", "summary": "原材料照片与生产记录按项目版本一一绑定。", "fields": [{"label": "原料", "value": ctx.equipment.material}, {"label": "状态", "value": "批次记录"}], "imageIds": [original_ids["raw-material"]], "evidenceRefs": [evidence_by_material[original_ids["raw-material"]], *fact_by_key["process_completeness"]["evidenceRefs"]], "sourceLabel": SOURCE_LABEL, "isSimulated": True},
            {"id": f"stage-{ctx.project_id}-process", "stage": "process", "title": ctx.equipment.process, "summary": "工艺原图、电费、工单和完工记录按日勾稽。", "fields": [{"label": "设备", "value": ctx.equipment.model}, {"label": "流程", "value": ctx.equipment.process}], "imageIds": [original_ids["process"], original_ids["equipment-line"]], "evidenceRefs": [evidence_by_material[original_ids["process"]], *fact_by_key["electricity_output_match"]["evidenceRefs"]], "sourceLabel": SOURCE_LABEL, "isSimulated": True},
            {"id": f"stage-{ctx.project_id}-finished", "stage": "finished-product", "title": f"{ctx.equipment.product}完工", "summary": "成品原图与完工绝对量按同一项目版本绑定。", "fields": [{"label": "产品", "value": ctx.equipment.product}, {"label": "口径", "value": "完工绝对量"}], "imageIds": [original_ids["finished-product"]], "evidenceRefs": [evidence_by_material[original_ids["finished-product"]], *fact_by_key["output_consistency"]["evidenceRefs"]], "sourceLabel": SOURCE_LABEL, "isSimulated": True},
        ],
        "productionEnergy": {"status": "available", "electricityMetric": "usage", "electricityUnit": "kWh", "outputMetric": "absolute", "outputUnit": "件", "aggregation": "sum", "points": energy_points, "message": "用电量与完工产量均由日观察值按月求和。", "sourceLabel": SOURCE_LABEL, "isSimulated": True},
        "referenceImages": references,
        "onsiteAssets": [
            {"id": f"asset-{ctx.project_id}-{category}", "label": label, "kind": "image", "collectionStatus": "collected", "materialId": original_ids[category], "sourceLabel": "项目级脱敏模拟原件；不是客户现场拍摄", "evidenceRefs": [evidence_by_material[original_ids[category]]], "lazyLoad": True, "isSimulated": True}
            for category, label in (
                ("site", "厂区总览"),
                ("site-overhead", "厂区俯视图"),
                ("site-front", "厂区正面平视图"),
                ("site-left", "厂区左侧平视图"),
                ("site-right", "厂区右侧平视图"),
                ("site-rear", "厂区背面平视图"),
                ("equipment-line", "设备与产线"),
                ("equipment-front", "设备正视图"),
                ("equipment-side", "设备侧视图"),
                ("equipment-rear", "设备背视图"),
            )
        ],
        "corrections": [], "determinations": determination_payloads, "reviewEvents": review_events,
        "layout": {"navigationWidth": 212, "materialWidth": 520, "collaborationHeight": 175, "navigationCollapsed": False, "middleCollapsed": False, "materialCollapsed": False, "collaborationCollapsed": False, "businessCollapsed": False, "policyCollapsed": False, "riskCollapsed": False, "activeDimensionId": "compliance"},
    }
    validate_locators(materials, registry.items)
    evidence_ids = {item["id"] for item in registry.items}
    if len(evidence_ids) != len(registry.items):
        raise AssertionError("generated evidence ids must be unique")
    unknown_refs = collect_evidence_refs(workbench) - evidence_ids
    if unknown_refs:
        raise AssertionError(f"generated project contains unknown evidence refs: {sorted(unknown_refs)[:3]}")
    catalog = {
        "projectId": ctx.project_id, "projectNo": ctx.project_no, "companyName": ctx.company_name,
        "companyShortName": ctx.company_short_name, "region": ctx.region, "industry": ctx.industry.name,
        "durationDays": 7 + index % 22, "store": ctx.store, "salesperson": ctx.salesperson,
        "amountWan": project_amount_wan, "financingType": "设备融资",
        "materialStatus": "待补材料" if ctx.pattern == "confirm" else "人工复核" if assessment.risk_level in {"risk", "forbid"} else "材料齐备",
        "createdAt": ctx.created_at, "timeBucket": ctx.created_at[:7], "riskLevel": assessment.risk_level,
        "riskBand": RISK_BAND_LABELS[assessment.risk_level], "decisionGrade": assessment.decision_grade,
        "dimensions": dimensions, "isSimulated": True,
    }
    return GeneratedProjectBundle(
        catalog=catalog,
        workbench=workbench,
        dimension_series=dimension_series,
        selection_groups=tuple(selection_groups),
        generation={"seed": seed, "index": index, "pattern": ctx.pattern, "version": GENERATOR_VERSION, "source": "deterministic_business_rules", "sourceLabel": SOURCE_LABEL, "disclaimer": DISCLAIMER, "isSimulated": True},
    )


def generate_project_bundles(
    seed: int = DEFAULT_GENERATOR_SEED,
    count: int = DEFAULT_PROJECT_COUNT,
    profile: str = "varied",
) -> tuple[dict[str, Any], ...]:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    if isinstance(count, bool) or not isinstance(count, int) or count < DEFAULT_PROJECT_COUNT:
        raise ValueError(f"count must be an integer >= {DEFAULT_PROJECT_COUNT}")
    if profile not in {"standard", "varied"}:
        raise ValueError("profile must be standard or varied")
    return tuple(generate_project_bundle(seed, index, profile).to_mapping() for index in range(count))


def generate_seed_bundles(
    seed: int = DEFAULT_GENERATOR_SEED,
    count: int = DEFAULT_PROJECT_COUNT,
) -> tuple[dict[str, Any], ...]:
    return generate_project_bundles(seed=seed, count=count, profile="varied")


def seed_bundles() -> tuple[dict[str, Any], ...]:
    return generate_project_bundles(profile="varied")


class WorkbenchGenerator:
    def __init__(self, seed: int = DEFAULT_GENERATOR_SEED, count: int = DEFAULT_PROJECT_COUNT, profile: str = "standard") -> None:
        self.seed = seed
        self.count = count
        self.profile = profile
        self._bundles: tuple[dict[str, Any], ...] | None = None

    @property
    def identity(self) -> str:
        return f"{GENERATOR_VERSION}:{self.profile}:{self.seed}:{self.count}"

    def seed_bundles(self) -> tuple[dict[str, Any], ...]:
        if self._bundles is None:
            self._bundles = generate_project_bundles(self.seed, self.count, self.profile)
        return self._bundles

    def query_dimension_series(self, request: Any) -> dict[str, Any] | None:
        if hasattr(request, "model_dump"):
            request_mapping = request.model_dump(by_alias=True, mode="json")
        elif isinstance(request, Mapping):
            request_mapping = dict(request)
        else:
            raise TypeError("dimension-series request must be a mapping or Pydantic model")
        project_id = request_mapping.get("projectId")
        for bundle in self.seed_bundles():
            if bundle["catalog"]["projectId"] != project_id:
                continue
            for series in bundle["dimensionSeries"]:
                if series["dimensionId"] == request_mapping.get("dimensionId"):
                    return aggregate_dimension_series(series, request_mapping)
            return None
        return None


def create_workbench_generator(settings: Any = None) -> WorkbenchGenerator:
    seed = getattr(settings, "generator_seed", DEFAULT_GENERATOR_SEED) if settings is not None else DEFAULT_GENERATOR_SEED
    profile = getattr(settings, "generator_profile", "standard") if settings is not None else "standard"
    return WorkbenchGenerator(seed=int(seed), count=DEFAULT_PROJECT_COUNT, profile=str(profile))


def _dimension_detail_payload(
    *,
    ctx: _Context,
    facts: Mapping[str, Any],
    assessment_by_id: Mapping[str, Any],
    fact_by_key: Mapping[str, Mapping[str, Any]],
    refs: Any,
    metric: Any,
    breakdown: Any,
    segment: Any,
    structure_refs: Mapping[str, str],
    derived: Mapping[str, Any],
    schedule: Sequence[Mapping[str, float | int]],
    schedule_refs: Sequence[str],
    production_points: Sequence[Mapping[str, Any]],
    payroll_points: Sequence[Mapping[str, Any]],
    revenue_compositions: Sequence[Mapping[str, Any]],
    debt_compositions: Sequence[Mapping[str, Any]],
    monthly: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    cashflow_compositions = []
    for group_id, label in (("cashflow-inflow-parties", "流入方"), ("cashflow-outflow-parties", "流出方")):
        group_keys = [key for key in structure_refs if key.startswith(f"{group_id}-")]
        total = float(derived["cashflow_in"] if "inflow" in group_id else derived["cashflow_out"])
        shares = (36.0, 28.0, 21.0, 15.0)
        allocated = [round(total * share / 100, 2) for share in shares[:-1]]
        allocated.append(round(total - sum(allocated), 2))
        cashflow_compositions.append({"id": group_id, "label": label, "segments": [segment(item_id, f"系统生成·{ctx.industry.short_name}{index + 1}", value, "万元", note=f"观察期份额{shares[index]:.0f}%") for index, (item_id, value) in enumerate(zip(group_keys, allocated))]})

    debt_schedule_points = []
    for index, (point, evidence_ref) in enumerate(zip(schedule[:12], schedule_refs[:12]), start=1):
        due_wan = round(float(point["rent"]) / 10_000, 2)
        capacity_wan = round(due_wan * float(facts["debt_service_coverage"]), 2)
        debt_schedule_points.append({
            "id": f"debt-repayment-{index:02d}",
            "label": f"第{index}期",
            "note": "本项目租金计划与规则生成偿还能力比较",
            "measures": [
                {"id": f"debt-repayment-{index:02d}-due", "label": "到期负债", "value": due_wan, "unit": "万元", "evidenceRefs": [evidence_ref]},
                {"id": f"debt-repayment-{index:02d}-capacity", "label": "可偿还能力", "value": capacity_wan, "unit": "万元", "evidenceRefs": [evidence_ref, *refs("debt_service_coverage")]},
            ],
        })

    return [
        {
            "dimensionId": "compliance", "visual": "subject-network", "defaultView": "visual", "availableViews": ["visual", "table"], "unit": "项",
            "metrics": [
                metric("compliance-registration", "登记状态", "有效" if facts["registration_valid"] else "异常", "主体登记状态", "registration_valid"),
                metric("compliance-identity", "身份一致性", f"{float(facts['identity_consistency']):.1f}%", "多证据交叉核验", "identity_consistency"),
                metric("compliance-litigation", "涉诉记录", f"{int(facts['litigation_count'])} 项", "只作单项目规则输入", "litigation_count"),
            ],
            "series": [], "seriesGroups": None, "compositions": None,
            "breakdown": [breakdown("compliance-prohibited", "禁入状态", "命中" if facts["prohibited_status"] else "未命中", "已定位规则事实", "prohibited_status"), breakdown("compliance-registry", "主体登记", "已核验" if facts["registration_valid"] else "异常", "精确 locator", "registration_valid")],
            "conclusion": assessment_by_id["compliance"].summary, "sourceLabel": SOURCE_LABEL, "isSimulated": True,
        },
        {
            "dimensionId": "transaction", "visual": "transaction-structure", "defaultView": "visual", "availableViews": ["visual", "table"], "unit": "万元",
            "metrics": [
                metric("transaction-supplier-rating", "供应商评级", str(facts["supplier_rating"]), "规则生成准入评级", "supplier_rating"),
                metric("transaction-brand-rating", "品牌评级", str(facts["brand_rating"]), "规则生成品牌评级", "brand_rating"),
                metric("transaction-project-amount", "项目金额", f"{float(fact_by_key['project_amount_wan']['value']):,.2f} 万", "合同设备合价", "project_amount_wan"),
                metric("transaction-financing-ratio", "融资成数", f"{float(facts['financing_ratio']) * 100:.1f}%", "融资金额 ÷ 项目金额", "financing_ratio"),
                metric("transaction-financed-amount", "融资金额", f"{float(fact_by_key['financed_amount_wan']['value']):,.2f} 万", "由项目金额和融资成数推导", "financed_amount_wan"),
                metric("transaction-term", "期限", f"{int(facts['term_months'])} 月", "租金计划期限", "term_months"),
                metric("transaction-repayment-risk", "还款结构风险", f"{repayment_structure_label(schedule)} · {classify_repayment_structure(schedule)}", "实际还款计划推导；前高后低最安全、均衡其次、前低后高最危险", "repayment"),
            ],
            "series": [{"id": f"transaction-rent-{point['period']}", "label": f"第{point['period']}期", "note": "实际租金计划", "measures": [{"id": f"transaction-rent-{point['period']}-rent", "label": "租金", "value": float(point["rent"]), "unit": "元", "evidenceRefs": [schedule_refs[index]]}]} for index, point in enumerate(schedule[:12])],
            "seriesGroups": None, "compositions": None,
            "breakdown": [breakdown("transaction-down-payment", "首付款", f"{float(fact_by_key['down_payment_wan']['value']):,.2f} 万", "项目金额减融资金额", "down_payment_wan"), breakdown("transaction-structure", "交易结构", "直租", "设备融资结构", "financing_ratio")],
            "conclusion": assessment_by_id["transaction"].summary, "sourceLabel": SOURCE_LABEL, "isSimulated": True,
        },
        {
            "dimensionId": "production", "visual": "production-series", "defaultView": "visual", "availableViews": ["visual", "table"], "unit": "运营事实",
            "metrics": [metric("production-utilization", "设备利用率", f"{float(facts['equipment_utilization']) * 100:.1f}%", "日观察值平均", "equipment_utilization"), metric("production-energy-match", "用电产量匹配", f"{float(facts['electricity_output_match']) * 100:.1f}%", "规则核验值", "electricity_output_match"), metric("production-process", "工艺完整度", f"{float(facts['process_completeness']) * 100:.1f}%", "流程记录完整度", "process_completeness")],
            "series": production_points, "seriesGroups": [{"id": "production-payroll", "label": "人员工资", "points": payroll_points}], "compositions": None,
            "breakdown": [breakdown("production-staff", "人员稳定", f"{float(facts['staff_stability']) * 100:.1f}%", "日工资及在岗观察", "staff_stability"), breakdown("production-output", "产量连续性", f"{float(facts['output_consistency']) * 100:.1f}%", "完工产量观察", "output_consistency")],
            "conclusion": assessment_by_id["production"].summary, "sourceLabel": SOURCE_LABEL, "isSimulated": True,
        },
        {
            "dimensionId": "revenue", "visual": "revenue-series", "defaultView": "visual", "availableViews": ["visual", "table"], "unit": "万元",
            "metrics": [
                metric("revenue-income-metric", "年度营收", f"{float(derived['annual_revenue']):,.2f} 万", "观察期按公历天数年化的规则生成值", "annual_revenue"),
                metric("revenue-net-profit-metric", "净利润", f"{float(derived['net_profit']):,.2f} 万", "年度营收扣除费用", "net_profit"),
                metric("revenue-net-margin-metric", "净利率", f"{float(facts['net_margin']) * 100:.1f}%", "净利润 ÷ 年度营收", "net_margin"),
                metric("revenue-rent-first-12-metric", "前12期项目租金", f"{float(derived['first_twelve_rent_wan']):,.4f} 万", "实际租金计划前12期合计", "first_twelve_rent_wan"),
                metric("revenue-rent-coverage-metric", "租金覆盖倍数", f"{float(derived['rent_coverage']):,.2f}×", "净利润 ÷ 前12期项目租金", "derived_rent_coverage"),
            ],
            "series": monthly["revenue"], "seriesGroups": None, "compositions": revenue_compositions,
            "breakdown": [breakdown("revenue-orders", "订单收入覆盖", f"{float(facts['order_income_coverage']) * 100:.1f}%", "订单与确认收入交叉核验", "order_income_coverage"), breakdown("revenue-invoices", "开票收入比", f"{float(facts['invoice_income_ratio']) * 100:.1f}%", "发票与确认收入交叉核验", "invoice_income_ratio"), breakdown("revenue-collections", "回款开票比", f"{float(facts['collection_invoice_ratio']) * 100:.1f}%", "回款与发票交叉核验", "collection_invoice_ratio")],
            "conclusion": assessment_by_id["revenue"].summary, "sourceLabel": SOURCE_LABEL, "isSimulated": True,
        },
        {
            "dimensionId": "debt", "visual": "debt-structure", "defaultView": "visual", "availableViews": ["visual", "table"], "unit": "万元",
            "metrics": [
                metric("debt-credit-metric", "征信负债", f"{float(derived['total_debt']):,.2f} 万", "企业与个人负债合计", "total_debt"),
                metric("debt-exposure-history", "历史存量", f"{float(derived['history_exposure']):,.2f}W", "项目既有敞口", "history_exposure"),
                metric("debt-exposure-current", "本次融资", f"{float(derived['current_exposure']):,.2f}W", "本次融资金额", "current_exposure"),
                metric("debt-exposure-total", "项目总敞口", f"{float(derived['total_exposure']):,.2f}W", "历史存量 + 本次融资；全局上限1000W", "total_exposure"),
                metric("debt-exposure-deduplication", "重复融资核验", "待人工核验" if fact_by_key["duplicate_registration"]["evidenceRefs"][0].endswith("duplicate-registration") and ctx.pattern == "confirm" else ("存在" if facts["duplicate_registration"] else "未见"), "无 locator 时显式 pending", "duplicate_registration"),
            ],
            "series": monthly["debt"], "seriesGroups": [{"id": "debt-repayment", "label": "未来12期偿债计划", "points": debt_schedule_points}], "compositions": debt_compositions,
            "breakdown": [breakdown("debt-ratio", "负债营收比", f"{float(facts['debt_revenue_ratio']) * 100:.1f}%", "负债 ÷ 年化营收", "debt_revenue_ratio"), breakdown("debt-guarantee", "担保义务", f"{float(facts['guarantee_obligation_ratio']) * 100:.1f}%", "不是第七维，仅为负债事实", "guarantee_obligation_ratio")],
            "conclusion": assessment_by_id["debt"].summary, "sourceLabel": SOURCE_LABEL, "isSimulated": True,
        },
        {
            "dimensionId": "cashflow", "visual": "cashflow-series", "defaultView": "visual", "availableViews": ["visual", "table"], "unit": "万元",
            "metrics": [metric("cashflow-in", "观察期流入", f"{float(derived['cashflow_in']):,.2f} 万", "日流入求和", "cashflow_in"), metric("cashflow-out", "观察期流出", f"{float(derived['cashflow_out']):,.2f} 万", "日流出求和", "cashflow_out"), metric("cashflow-net", "观察期净额", f"{float(derived['cashflow_net']):,.2f} 万", "流入减流出", "cashflow_net"), metric("cashflow-anomalies-metric", "异常笔数", f"{int(derived['cashflow_anomalies'])} 笔", "逐日异常标识求和", "cashflow_anomalies")],
            "series": monthly["cashflow"], "seriesGroups": None, "compositions": cashflow_compositions,
            "breakdown": [breakdown("cashflow-authenticity", "收支真实性", f"{float(facts['cashflow_revenue_match']) * 100:.1f}%", "流水与营收匹配", "cashflow_revenue_match"), breakdown("cashflow-operating-match", "经营匹配", f"{float(facts['operating_counterparty_share']) * 100:.1f}%", "经营对手方占比", "operating_counterparty_share"), breakdown("cashflow-anomalies", "异常流水", f"{int(derived['cashflow_anomalies'])} 笔", "只进入人工核验，不泄漏审批结果", "cashflow_anomaly_rate")],
            "conclusion": assessment_by_id["cashflow"].summary, "sourceLabel": SOURCE_LABEL, "isSimulated": True,
        },
    ]


__all__ = [
    "DEFAULT_GENERATOR_SEED",
    "DEFAULT_PROJECT_COUNT",
    "GENERATOR_VERSION",
    "GeneratedProjectBundle",
    "WorkbenchGenerator",
    "create_workbench_generator",
    "generate_project_bundle",
    "generate_project_bundles",
    "generate_seed_bundles",
    "seed_bundles",
]
