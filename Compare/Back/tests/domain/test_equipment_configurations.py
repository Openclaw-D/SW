"""Contract and anti-mixing tests for equipment configuration fixtures."""

from __future__ import annotations

import pytest

from app.contracts.workbench import EquipmentConfigurationRow as RowContract
from app.fixtures.equipment_configurations import (
    CONFIGURATION_SOURCE_LABEL,
    CONFIGURATION_TONES,
    EQUIPMENT_CONFIGURATION_PROFILES,
    build_equipment_configuration,
)


ROW_FIELDS = {
    "id",
    "factVersionId",
    "label",
    "unit",
    "current",
    "median",
    "range",
    "sourceLabel",
    "tone",
    "evidenceRefs",
}

PROFILE_EXPECTATIONS = (
    ("metal_processing", "五轴加工中心", "RG-850", ("X轴行程", "主轴最高转速", "定位精度", "刀库容量", "转台直径")),
    ("metal_processing", "车铣复合中心", "HL-1200", ("最大车削直径", "主轴最高转速", "动力刀塔转速", "定位精度", "刀塔工位")),
    ("metal_processing", "立式加工中心", "DH-650", ("X轴行程", "主轴最高转速", "工作台承重", "定位精度", "刀库容量")),
    ("plastic_processing", "全电动注塑机", "SN-280E", ("锁模力", "理论注射容积", "螺杆直径", "空循环时间", "装机功率")),
    ("plastic_processing", "精密注塑成型单元", "NH-450", ("锁模力", "理论注射容积", "重量重复精度", "标准成型周期", "机械手轴数")),
    ("plastic_processing", "节能伺服注塑机", "XY-200", ("锁模力", "理论注射容积", "螺杆直径", "单位制品能耗", "装机功率")),
    ("textile", "高速针织圆机", "YS-72", ("针筒直径", "针距", "成圈路数", "最高转速", "装机功率")),
    ("textile", "喷气织机生产线", "JW-900", ("公称筘幅", "最高织造速度", "综框数量", "单台耗气量", "单台装机功率")),
    ("textile", "电脑横机", "QY-520", ("针床宽度", "针距", "机头最高速度", "纱嘴数量", "装机功率")),
    ("printing_packaging", "六色胶印机", "HC-106", ("最大纸张宽度", "最高印刷速度", "印刷色组", "印版厚度", "装机功率")),
    ("printing_packaging", "高速凹版印刷机", "QH-1250", ("有效印刷宽度", "最高印刷速度", "印刷色组", "张力控制精度", "干燥系统功率")),
    ("printing_packaging", "窄幅柔版印刷机", "FG-420", ("有效印刷宽度", "最高印刷速度", "印刷色组", "套印精度", "装机功率")),
    ("electronics_manufacturing", "高速SMT贴片线", "XL-SMT8", ("理论贴装速度", "贴装精度", "供料器槽位", "最大PCB宽度", "整线装机功率")),
    ("electronics_manufacturing", "柔性电子装联线", "CG-FLEX", ("理论贴装速度", "贴装精度", "产品换线时间", "最大PCB宽度", "整线装机功率")),
    ("electronics_manufacturing", "中速SMT贴片线", "QY-SMT5", ("理论贴装速度", "贴装精度", "供料器槽位", "最大PCB宽度", "整线装机功率")),
    ("glass_processing", "连续式钢化炉", "CM-2448", ("最大玻璃宽度", "适用玻璃厚度", "额定加热温度", "最大传输速度", "装机功率")),
    ("glass_processing", "玻璃精密镀膜线", "JJ-2200", ("最大镀膜宽度", "最大线速度", "工作真空度", "膜厚均匀性", "装机功率")),
    ("glass_processing", "节能钢化炉", "AL-1836", ("最大玻璃宽度", "适用玻璃厚度", "额定加热温度", "单位面积能耗", "装机功率")),
)


def _build(
    industry_id: str,
    equipment_name: str,
    model: str,
    *,
    seed: int,
) -> list[dict[str, object]]:
    return build_equipment_configuration(
        industry_id,
        equipment_name,
        model,
        "simulated-customer-001",
        seed,
        "normal_reviewable",
    )


def test_catalogue_covers_six_industries_and_all_exact_equipment_profiles() -> None:
    expected_names = {item[1] for item in PROFILE_EXPECTATIONS}
    expected_industries = {item[0] for item in PROFILE_EXPECTATIONS}

    assert len(PROFILE_EXPECTATIONS) == 18
    assert expected_industries == {
        "metal_processing",
        "plastic_processing",
        "textile",
        "printing_packaging",
        "electronics_manufacturing",
        "glass_processing",
    }
    assert set(EQUIPMENT_CONFIGURATION_PROFILES) == expected_names
    assert all(
        sum(profile.industry_id == industry for profile in EQUIPMENT_CONFIGURATION_PROFILES.values()) == 3
        for industry in expected_industries
    )


@pytest.mark.parametrize(
    ("industry_id", "equipment_name", "model", "expected_labels"),
    PROFILE_EXPECTATIONS,
)
def test_every_profile_returns_exact_front_rows_without_parameter_mixing(
    industry_id: str,
    equipment_name: str,
    model: str,
    expected_labels: tuple[str, ...],
) -> None:
    rows = _build(industry_id, equipment_name, model, seed=317)
    repeated = _build(industry_id, equipment_name, model, seed=317)

    assert rows == repeated
    assert tuple(row["label"] for row in rows) == expected_labels
    assert len({row["id"] for row in rows}) == len(rows)
    for row in rows:
        assert set(row) == ROW_FIELDS
        assert RowContract.model_validate(row).model_dump(by_alias=True) == row
        assert row["factVersionId"] is None
        assert row["evidenceRefs"] == []
        assert row["tone"] in CONFIGURATION_TONES
        assert row["current"].endswith(row["unit"])
        assert row["median"].endswith(row["unit"])
        assert row["range"].endswith(row["unit"])
        assert "–" in row["range"]
        assert row["sourceLabel"] == CONFIGURATION_SOURCE_LABEL
        assert "模拟" in row["sourceLabel"]
        assert "非厂商核验" in row["sourceLabel"]
        assert "非统计样本" in row["sourceLabel"]


@pytest.mark.parametrize(
    ("industry_id", "equipment_name", "model", "_expected_labels"),
    PROFILE_EXPECTATIONS,
)
def test_different_seeds_change_each_equipment_profile(
    industry_id: str,
    equipment_name: str,
    model: str,
    _expected_labels: tuple[str, ...],
) -> None:
    first = _build(industry_id, equipment_name, model, seed=317)
    changed = _build(industry_id, equipment_name, model, seed=318)

    assert [row["current"] for row in first] != [row["current"] for row in changed]
    stable_fields = ("id", "factVersionId", "label", "unit", "median", "range", "sourceLabel", "evidenceRefs")
    assert [tuple(row[field] for field in stable_fields) for row in first] == [
        tuple(row[field] for field in stable_fields) for row in changed
    ]


@pytest.mark.parametrize(
    ("industry_id", "equipment_name", "model", "_expected_labels"),
    PROFILE_EXPECTATIONS,
)
def test_wrong_industry_or_model_is_rejected_instead_of_falling_back(
    industry_id: str,
    equipment_name: str,
    model: str,
    _expected_labels: tuple[str, ...],
) -> None:
    wrong_industry = "textile" if industry_id != "textile" else "metal_processing"

    with pytest.raises(ValueError, match="exact industry/equipment/model"):
        build_equipment_configuration(
            wrong_industry,
            equipment_name,
            model,
            "simulated-customer-001",
            317,
            "normal_reviewable",
        )
    with pytest.raises(ValueError, match="exact industry/equipment/model"):
        build_equipment_configuration(
            industry_id,
            equipment_name,
            f"{model}-WRONG",
            "simulated-customer-001",
            317,
            "normal_reviewable",
        )


def test_unknown_equipment_and_empty_generation_inputs_are_explicit_errors() -> None:
    with pytest.raises(ValueError, match="unknown equipment profile"):
        build_equipment_configuration(
            "textile",
            "不存在的设备",
            "UNKNOWN",
            "simulated-customer-001",
            317,
            "normal_reviewable",
        )
    with pytest.raises(ValueError, match="customer_id"):
        build_equipment_configuration(
            "textile", "高速针织圆机", "YS-72", "", 317, "normal_reviewable"
        )
    with pytest.raises(ValueError, match="risk_pattern"):
        build_equipment_configuration(
            "textile", "高速针织圆机", "YS-72", "simulated-customer-001", 317, " "
        )
