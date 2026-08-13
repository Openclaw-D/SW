from __future__ import annotations

DIMENSION_IDS: tuple[str, ...] = (
    "compliance",
    "transaction",
    "production",
    "revenue",
    "debt",
    "cashflow",
)

DIMENSION_NAMES = {
    "compliance": "合规",
    "transaction": "交易",
    "production": "生产",
    "revenue": "营收",
    "debt": "负债",
    "cashflow": "流水",
}

DIMENSION_FULL_NAMES = {
    "compliance": "主体合规",
    "transaction": "交易结构",
    "production": "生产经营",
    "revenue": "营收核验",
    "debt": "负债核验",
    "cashflow": "流水核验",
}

RISK_BAND_LABELS = {
    "support": "支持",
    "attention": "关注",
    "confirm": "核实",
    "risk": "风险",
    "forbid": "禁止",
}

SOURCE_LABEL = (
    "完整脱敏的确定性业务规则生成数据；仅用于单项目事实核验与交互验证，"
    "不代表真实客户、厂商核验参数、历史统计样本或统计模型"
)

DISCLAIMER = (
    "本项目全部身份、材料、金额、评分、规则结果与时间序列均由确定性业务规则生成。"
    "输出不是审批结论，不具备统计验证、违约概率预测或真实客户事实效力；"
    "最终判断必须由有权限的人工审查者结合原始材料完成。"
)

RULE_VERSION = "compare-business-rules-2026.08"
GENERATOR_VERSION = "p4-back-3-workbench-v1"

__all__ = [
    "DIMENSION_FULL_NAMES",
    "DIMENSION_IDS",
    "DIMENSION_NAMES",
    "DISCLAIMER",
    "GENERATOR_VERSION",
    "RISK_BAND_LABELS",
    "RULE_VERSION",
    "SOURCE_LABEL",
]
