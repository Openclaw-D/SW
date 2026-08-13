from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EquipmentFixture:
    equipment: str
    model: str
    brand: str
    process: str
    product: str
    material: str
    capacity_unit: str


@dataclass(frozen=True)
class IndustryFixture:
    id: str
    name: str
    short_name: str
    regions: tuple[str, ...]
    equipments: tuple[EquipmentFixture, ...]


INDUSTRIES: tuple[IndustryFixture, ...] = (
    IndustryFixture("metal_processing", "金属精密加工", "精工", ("华东", "华南", "华中"), (
        EquipmentFixture("五轴加工中心", "RG-850", "规则生成品牌M1", "五轴铣削与终检", "精密结构件", "合金棒料", "件/日"),
        EquipmentFixture("车铣复合中心", "HL-1200", "规则生成品牌M2", "车铣复合与测量", "轴套零件", "不锈钢棒料", "件/日"),
        EquipmentFixture("立式加工中心", "DH-650", "规则生成品牌M3", "铣削钻孔与抽检", "机加工组件", "铝合金坯料", "件/日"),
    )),
    IndustryFixture("plastic_processing", "塑料制品加工", "塑成", ("华东", "华南", "西南"), (
        EquipmentFixture("全电动注塑机", "SN-280E", "规则生成品牌P1", "注塑成型与外观检验", "精密塑件", "工程塑料粒子", "件/日"),
        EquipmentFixture("精密注塑成型单元", "NH-450", "规则生成品牌P2", "成型与自动取件", "结构塑件", "改性塑料粒子", "件/日"),
        EquipmentFixture("节能伺服注塑机", "XY-200", "规则生成品牌P3", "伺服注塑与批次检验", "通用塑件", "塑料粒子", "件/日"),
    )),
    IndustryFixture("textile", "纺织制造", "织造", ("华东", "华南", "华中"), (
        EquipmentFixture("高速针织圆机", "YS-72", "规则生成品牌T1", "针织与坯布检验", "针织坯布", "纱线", "千克/日"),
        EquipmentFixture("喷气织机生产线", "JW-900", "规则生成品牌T2", "整经织造与验布", "机织面料", "经纬纱", "米/日"),
        EquipmentFixture("电脑横机", "QY-520", "规则生成品牌T3", "编织与成衣片检验", "针织衣片", "纱线", "片/日"),
    )),
    IndustryFixture("printing_packaging", "印刷包装", "印包", ("华东", "华南", "华北"), (
        EquipmentFixture("六色胶印机", "HC-106", "规则生成品牌R1", "制版印刷与色差检验", "彩色包装", "纸张与油墨", "张/日"),
        EquipmentFixture("高速凹版印刷机", "QH-1250", "规则生成品牌R2", "凹版印刷与复合", "软包装膜", "薄膜与油墨", "米/日"),
        EquipmentFixture("窄幅柔版印刷机", "FG-420", "规则生成品牌R3", "柔版印刷与模切", "标签制品", "标签基材", "米/日"),
    )),
    IndustryFixture("electronics_manufacturing", "电子制造", "电子", ("华东", "华南", "西南"), (
        EquipmentFixture("高速SMT贴片线", "XL-SMT8", "规则生成品牌E1", "印刷贴装回流与AOI", "电子组件", "PCB与元器件", "片/日"),
        EquipmentFixture("柔性电子装联线", "CG-FLEX", "规则生成品牌E2", "柔性换线与装联测试", "控制组件", "PCB与元器件", "片/日"),
        EquipmentFixture("中速SMT贴片线", "QY-SMT5", "规则生成品牌E3", "贴装回流与测试", "电子模组", "PCB与元器件", "片/日"),
    )),
    IndustryFixture("glass_processing", "玻璃深加工", "玻璃", ("华东", "华南", "华北"), (
        EquipmentFixture("连续式钢化炉", "CM-2448", "规则生成品牌G1", "切割磨边钢化与检验", "钢化玻璃", "玻璃原片", "平方米/日"),
        EquipmentFixture("玻璃精密镀膜线", "JJ-2200", "规则生成品牌G2", "清洗镀膜与光学检验", "镀膜玻璃", "玻璃原片", "平方米/日"),
        EquipmentFixture("节能钢化炉", "AL-1836", "规则生成品牌G3", "钢化冷却与碎片检验", "节能钢化玻璃", "玻璃原片", "平方米/日"),
    )),
)

INDUSTRY_IDS = tuple(item.id for item in INDUSTRIES)
INDUSTRY_BY_ID = {item.id: item for item in INDUSTRIES}

__all__ = ["EquipmentFixture", "INDUSTRIES", "INDUSTRY_BY_ID", "INDUSTRY_IDS", "IndustryFixture"]
