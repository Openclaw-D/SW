from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.contracts.base import ContractModel
from app.contracts.workbench import (
    DecisionGrade,
    DimensionDefinition,
    RiskLevel,
)


ProjectMaterialStatus = Literal["材料齐备", "待补材料", "人工复核"]
ProjectRiskBand = Literal["禁止", "风险", "核实", "关注", "支持"]
RISK_BAND_LABELS: dict[RiskLevel, ProjectRiskBand] = {
    "forbid": "禁止",
    "risk": "风险",
    "confirm": "核实",
    "attention": "关注",
    "support": "支持",
}


class ProjectCatalogItem(ContractModel):
    project_id: str
    project_no: str
    company_name: str
    company_short_name: str
    region: str
    industry: str
    duration_days: int = Field(ge=0)
    store: str
    salesperson: str
    amount_wan: float = Field(ge=0)
    financing_type: Literal["设备融资"]
    material_status: ProjectMaterialStatus
    created_at: datetime
    time_bucket: str
    risk_level: RiskLevel
    risk_band: ProjectRiskBand
    decision_grade: DecisionGrade
    dimensions: list[DimensionDefinition]
    is_simulated: bool

    @model_validator(mode="after")
    def validate_risk_band(self) -> "ProjectCatalogItem":
        if self.risk_band != RISK_BAND_LABELS[self.risk_level]:
            raise ValueError("riskBand must be derived from riskLevel")
        return self
