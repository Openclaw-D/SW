"""Deterministic equipment-configuration fixtures for the Compare workbench.

The catalogue deliberately maps one exact industry/equipment/model triple to
one parameter set.  Public or manufacturer material informed only which
parameter axes are useful to display.  Every numeric value below is a
business-rule-generated simulation anchor, not a manufacturer-verified value
or a statistical sample.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import random
from typing import Literal, TypedDict


EQUIPMENT_CONFIGURATION_CONTRACT_VERSION = "equipment-configuration-v1"
CONFIGURATION_SOURCE_LABEL = (
    "脱敏模拟业务规则锚点；公开规格仅用于参数轴选择，数值非厂商核验、非统计样本"
)
CONFIGURATION_TONES = frozenset({"positive", "neutral", "attention", "risk"})


class EquipmentConfigurationRow(TypedDict):
    id: str
    factVersionId: str | None
    label: str
    unit: str
    current: str
    median: str
    range: str
    sourceLabel: str
    tone: Literal["positive", "neutral", "attention", "risk"]
    evidenceRefs: list[str]


@dataclass(frozen=True)
class EquipmentParameterSpec:
    id: str
    label: str
    median: float
    low: float
    high: float
    unit: str
    decimals: int = 0


@dataclass(frozen=True)
class EquipmentConfigurationProfile:
    id: str
    industry_id: str
    equipment_name: str
    model: str
    parameters: tuple[EquipmentParameterSpec, ...]


def _spec(
    parameter_id: str,
    label: str,
    median: float,
    low: float,
    high: float,
    unit: str,
    decimals: int = 0,
) -> EquipmentParameterSpec:
    if not low <= median <= high:
        raise ValueError(f"invalid simulated range for {parameter_id}")
    return EquipmentParameterSpec(
        id=parameter_id,
        label=label,
        median=median,
        low=low,
        high=high,
        unit=unit,
        decimals=decimals,
    )


def _profile(
    profile_id: str,
    industry_id: str,
    equipment_name: str,
    model: str,
    *parameters: EquipmentParameterSpec,
) -> EquipmentConfigurationProfile:
    parameter_ids = tuple(parameter.id for parameter in parameters)
    if len(parameter_ids) != len(set(parameter_ids)):
        raise ValueError(f"duplicate parameter id in {profile_id}")
    return EquipmentConfigurationProfile(
        id=profile_id,
        industry_id=industry_id,
        equipment_name=equipment_name,
        model=model,
        parameters=tuple(parameters),
    )


_PROFILES = (
    _profile(
        "metal-five-axis",
        "metal_processing",
        "五轴加工中心",
        "RG-850",
        _spec("x-travel", "X轴行程", 850, 750, 950, "mm"),
        _spec("spindle-speed", "主轴最高转速", 18_000, 15_000, 24_000, "rpm"),
        _spec("position-accuracy", "定位精度", 5.0, 3.0, 8.0, "μm", 1),
        _spec("tool-capacity", "刀库容量", 40, 30, 60, "把"),
        _spec("rotary-table", "转台直径", 650, 500, 800, "mm"),
    ),
    _profile(
        "metal-turn-mill",
        "metal_processing",
        "车铣复合中心",
        "HL-1200",
        _spec("turning-diameter", "最大车削直径", 520, 420, 650, "mm"),
        _spec("main-spindle-speed", "主轴最高转速", 4_500, 3_500, 6_000, "rpm"),
        _spec("milling-speed", "动力刀塔转速", 10_000, 8_000, 12_000, "rpm"),
        _spec("position-accuracy", "定位精度", 6.0, 4.0, 9.0, "μm", 1),
        _spec("tool-positions", "刀塔工位", 12, 10, 16, "位"),
    ),
    _profile(
        "metal-vertical",
        "metal_processing",
        "立式加工中心",
        "DH-650",
        _spec("x-travel", "X轴行程", 650, 550, 800, "mm"),
        _spec("spindle-speed", "主轴最高转速", 12_000, 10_000, 18_000, "rpm"),
        _spec("table-load", "工作台承重", 600, 450, 850, "kg"),
        _spec("position-accuracy", "定位精度", 7.0, 5.0, 10.0, "μm", 1),
        _spec("tool-capacity", "刀库容量", 24, 20, 32, "把"),
    ),
    _profile(
        "plastic-all-electric",
        "plastic_processing",
        "全电动注塑机",
        "SN-280E",
        _spec("clamping-force", "锁模力", 2_800, 2_400, 3_200, "kN"),
        _spec("injection-volume", "理论注射容积", 760, 620, 920, "cm³"),
        _spec("screw-diameter", "螺杆直径", 55, 48, 65, "mm"),
        _spec("dry-cycle", "空循环时间", 2.6, 2.0, 3.5, "s", 1),
        _spec("installed-power", "装机功率", 58, 45, 72, "kW"),
    ),
    _profile(
        "plastic-precision-cell",
        "plastic_processing",
        "精密注塑成型单元",
        "NH-450",
        _spec("clamping-force", "锁模力", 4_500, 3_800, 5_200, "kN"),
        _spec("injection-volume", "理论注射容积", 1_450, 1_150, 1_750, "cm³"),
        _spec("repeatability", "重量重复精度", 0.25, 0.15, 0.40, "%", 2),
        _spec("cycle-time", "标准成型周期", 18, 14, 25, "s", 1),
        _spec("robot-axes", "机械手轴数", 5, 4, 6, "轴"),
    ),
    _profile(
        "plastic-servo",
        "plastic_processing",
        "节能伺服注塑机",
        "XY-200",
        _spec("clamping-force", "锁模力", 2_000, 1_600, 2_400, "kN"),
        _spec("injection-volume", "理论注射容积", 520, 420, 680, "cm³"),
        _spec("screw-diameter", "螺杆直径", 48, 42, 56, "mm"),
        _spec("specific-energy", "单位制品能耗", 0.48, 0.36, 0.62, "kWh/kg", 2),
        _spec("installed-power", "装机功率", 42, 32, 55, "kW"),
    ),
    _profile(
        "textile-circular-knitting",
        "textile",
        "高速针织圆机",
        "YS-72",
        _spec("cylinder-diameter", "针筒直径", 34, 30, 38, "英寸"),
        _spec("gauge", "针距", 28, 24, 32, "G"),
        _spec("feeders", "成圈路数", 72, 60, 96, "路"),
        _spec("rotation-speed", "最高转速", 32, 25, 40, "rpm"),
        _spec("installed-power", "装机功率", 7.5, 5.5, 11.0, "kW", 1),
    ),
    _profile(
        "textile-air-jet-loom",
        "textile",
        "喷气织机生产线",
        "JW-900",
        _spec("reed-width", "公称筘幅", 1_900, 1_700, 2_300, "mm"),
        _spec("weaving-speed", "最高织造速度", 1_050, 850, 1_250, "rpm"),
        _spec("heald-frames", "综框数量", 16, 12, 20, "片"),
        _spec("air-consumption", "单台耗气量", 1.25, 0.95, 1.60, "m³/min", 2),
        _spec("installed-power", "单台装机功率", 5.5, 4.0, 7.5, "kW", 1),
    ),
    _profile(
        "textile-flat-knitting",
        "textile",
        "电脑横机",
        "QY-520",
        _spec("needle-bed-width", "针床宽度", 52, 48, 60, "英寸"),
        _spec("gauge", "针距", 14, 12, 18, "G"),
        _spec("carriage-speed", "机头最高速度", 1.4, 1.1, 1.8, "m/s", 1),
        _spec("yarn-feeders", "纱嘴数量", 16, 12, 24, "个"),
        _spec("installed-power", "装机功率", 1.8, 1.2, 2.5, "kW", 1),
    ),
    _profile(
        "printing-six-color-offset",
        "printing_packaging",
        "六色胶印机",
        "HC-106",
        _spec("max-sheet-width", "最大纸张宽度", 1_060, 900, 1_180, "mm"),
        _spec("printing-speed", "最高印刷速度", 16_500, 14_000, 19_000, "张/h"),
        _spec("color-units", "印刷色组", 6, 6, 8, "色"),
        _spec("plate-thickness", "印版厚度", 0.30, 0.24, 0.40, "mm", 2),
        _spec("installed-power", "装机功率", 165, 135, 210, "kW"),
    ),
    _profile(
        "printing-gravure",
        "printing_packaging",
        "高速凹版印刷机",
        "QH-1250",
        _spec("printing-width", "有效印刷宽度", 1_250, 1_050, 1_450, "mm"),
        _spec("printing-speed", "最高印刷速度", 320, 250, 400, "m/min"),
        _spec("color-units", "印刷色组", 10, 8, 12, "色"),
        _spec("tension-accuracy", "张力控制精度", 0.50, 0.30, 0.80, "%", 2),
        _spec("drying-power", "干燥系统功率", 210, 170, 280, "kW"),
    ),
    _profile(
        "printing-narrow-flexo",
        "printing_packaging",
        "窄幅柔版印刷机",
        "FG-420",
        _spec("printing-width", "有效印刷宽度", 420, 330, 520, "mm"),
        _spec("printing-speed", "最高印刷速度", 180, 140, 240, "m/min"),
        _spec("color-units", "印刷色组", 8, 6, 10, "色"),
        _spec("register-accuracy", "套印精度", 0.12, 0.08, 0.20, "mm", 2),
        _spec("installed-power", "装机功率", 48, 36, 65, "kW"),
    ),
    _profile(
        "electronics-high-speed-smt",
        "electronics_manufacturing",
        "高速SMT贴片线",
        "XL-SMT8",
        _spec("placement-speed", "理论贴装速度", 120_000, 95_000, 150_000, "CPH"),
        _spec("placement-accuracy", "贴装精度", 35, 25, 50, "μm"),
        _spec("feeder-slots", "供料器槽位", 160, 120, 220, "站"),
        _spec("max-pcb-width", "最大PCB宽度", 510, 460, 610, "mm"),
        _spec("line-power", "整线装机功率", 145, 110, 190, "kW"),
    ),
    _profile(
        "electronics-flexible-line",
        "electronics_manufacturing",
        "柔性电子装联线",
        "CG-FLEX",
        _spec("placement-speed", "理论贴装速度", 85_000, 65_000, 110_000, "CPH"),
        _spec("placement-accuracy", "贴装精度", 28, 20, 40, "μm"),
        _spec("changeover-time", "产品换线时间", 18, 12, 28, "min"),
        _spec("max-pcb-width", "最大PCB宽度", 460, 400, 560, "mm"),
        _spec("line-power", "整线装机功率", 118, 90, 155, "kW"),
    ),
    _profile(
        "electronics-medium-speed-smt",
        "electronics_manufacturing",
        "中速SMT贴片线",
        "QY-SMT5",
        _spec("placement-speed", "理论贴装速度", 52_000, 40_000, 70_000, "CPH"),
        _spec("placement-accuracy", "贴装精度", 45, 35, 65, "μm"),
        _spec("feeder-slots", "供料器槽位", 96, 72, 140, "站"),
        _spec("max-pcb-width", "最大PCB宽度", 410, 350, 510, "mm"),
        _spec("line-power", "整线装机功率", 82, 62, 110, "kW"),
    ),
    _profile(
        "glass-continuous-tempering",
        "glass_processing",
        "连续式钢化炉",
        "CM-2448",
        _spec("max-glass-width", "最大玻璃宽度", 2_440, 2_100, 2_850, "mm"),
        _spec("glass-thickness", "适用玻璃厚度", 12, 4, 19, "mm"),
        _spec("heating-temperature", "额定加热温度", 690, 660, 720, "℃"),
        _spec("line-speed", "最大传输速度", 15, 11, 20, "m/min", 1),
        _spec("installed-power", "装机功率", 920, 720, 1_180, "kW"),
    ),
    _profile(
        "glass-precision-coating",
        "glass_processing",
        "玻璃精密镀膜线",
        "JJ-2200",
        _spec("coating-width", "最大镀膜宽度", 2_200, 1_800, 2_600, "mm"),
        _spec("line-speed", "最大线速度", 8.0, 5.0, 12.0, "m/min", 1),
        _spec("vacuum-pressure", "工作真空度", 0.005, 0.002, 0.010, "Pa", 3),
        _spec("film-uniformity", "膜厚均匀性", 2.0, 1.0, 3.5, "%", 1),
        _spec("installed-power", "装机功率", 680, 520, 880, "kW"),
    ),
    _profile(
        "glass-energy-tempering",
        "glass_processing",
        "节能钢化炉",
        "AL-1836",
        _spec("max-glass-width", "最大玻璃宽度", 1_830, 1_600, 2_200, "mm"),
        _spec("glass-thickness", "适用玻璃厚度", 10, 4, 15, "mm"),
        _spec("heating-temperature", "额定加热温度", 680, 650, 710, "℃"),
        _spec("specific-energy", "单位面积能耗", 3.6, 2.8, 4.8, "kWh/m²", 1),
        _spec("installed-power", "装机功率", 560, 420, 720, "kW"),
    ),
)


EQUIPMENT_CONFIGURATION_PROFILES = {
    profile.equipment_name: profile for profile in _PROFILES
}
if len(EQUIPMENT_CONFIGURATION_PROFILES) != len(_PROFILES):
    raise ValueError("equipment names must be globally unique")


_RISK_PATTERN_VARIABILITY = {
    "quality_stable": 0.45,
    "normal_reviewable": 0.85,
    "evidence_to_confirm": 1.15,
    "high_risk_blocked": 1.65,
    "support": 0.45,
    "attention": 0.80,
    "confirm": 1.05,
    "risk": 1.35,
    "forbid": 1.65,
    "支持": 0.45,
    "关注": 0.80,
    "核实": 1.05,
    "风险": 1.35,
    "禁止": 1.65,
}


def _risk_variability(risk_pattern: str) -> float:
    normalized = risk_pattern.strip().casefold().replace("-", "_")
    if not normalized:
        raise ValueError("risk_pattern must not be empty")
    if normalized in _RISK_PATTERN_VARIABILITY:
        return _RISK_PATTERN_VARIABILITY[normalized]
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return 0.55 + (digest[0] / 255) * 1.0


def _rng(*parts: object) -> random.Random:
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _round_value(value: float, decimals: int) -> float | int:
    rounded = round(value, decimals)
    return int(rounded) if decimals == 0 else rounded


def _format_value(value: float | int, decimals: int) -> str:
    if decimals == 0:
        return str(int(round(value)))
    return f"{float(value):.{decimals}f}"


def _display_value(value: float | int, decimals: int, unit: str) -> str:
    return f"{_format_value(value, decimals)} {unit}"


def _tone(
    current: float,
    spec: EquipmentParameterSpec,
) -> Literal["positive", "neutral", "attention", "risk"]:
    half_span = max((spec.high - spec.low) / 2, 0.000_001)
    distance = abs(current - spec.median) / half_span
    if distance <= 0.35:
        return "positive"
    if spec.low <= current <= spec.high:
        return "neutral"
    if distance <= 1.35:
        return "attention"
    return "risk"


def build_equipment_configuration(
    industry_id: str,
    equipment_name: str,
    model: str,
    customer_id: str,
    seed: int,
    risk_pattern: str,
) -> list[EquipmentConfigurationRow]:
    """Build deterministic Front-ready rows for one exact equipment profile.

    No industry-level or fuzzy fallback is allowed.  `factVersionId` and
    `evidenceRefs` remain empty because simulated benchmark anchors are not
    source evidence for a project fact.
    """

    profile = EQUIPMENT_CONFIGURATION_PROFILES.get(equipment_name)
    if profile is None:
        raise ValueError(f"unknown equipment profile: {equipment_name!r}")
    if profile.industry_id != industry_id or profile.model != model:
        raise ValueError(
            "equipment profile does not match exact industry/equipment/model "
            f"triple: {(industry_id, equipment_name, model)!r}"
        )
    if not customer_id:
        raise ValueError("customer_id must not be empty")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    if not isinstance(risk_pattern, str):
        raise TypeError("risk_pattern must be a string")

    variability = _risk_variability(risk_pattern)
    rows: list[EquipmentConfigurationRow] = []
    for spec in profile.parameters:
        generator = _rng(
            EQUIPMENT_CONFIGURATION_CONTRACT_VERSION,
            industry_id,
            equipment_name,
            model,
            customer_id,
            seed,
            risk_pattern,
            spec.id,
        )
        half_span = (spec.high - spec.low) / 2
        current = _round_value(
            max(
                0.0,
                spec.median
                + generator.uniform(-1.0, 1.0) * half_span * variability,
            ),
            spec.decimals,
        )
        rows.append(
            {
                "id": f"config-{profile.id}-{spec.id}",
                "factVersionId": None,
                "label": spec.label,
                "unit": spec.unit,
                "current": _display_value(current, spec.decimals, spec.unit),
                "median": _display_value(spec.median, spec.decimals, spec.unit),
                "range": (
                    f"{_format_value(spec.low, spec.decimals)}–"
                    f"{_display_value(spec.high, spec.decimals, spec.unit)}"
                ),
                "sourceLabel": CONFIGURATION_SOURCE_LABEL,
                "tone": _tone(float(current), spec),
                "evidenceRefs": [],
            }
        )
    return rows


__all__ = [
    "CONFIGURATION_SOURCE_LABEL",
    "CONFIGURATION_TONES",
    "EQUIPMENT_CONFIGURATION_CONTRACT_VERSION",
    "EQUIPMENT_CONFIGURATION_PROFILES",
    "EquipmentConfigurationProfile",
    "EquipmentConfigurationRow",
    "EquipmentParameterSpec",
    "build_equipment_configuration",
]
