import type { DimensionId, EvidenceReference, FactVersion } from "../contracts/workbench";

/**
 * 只使用当前公开契约中已有的事实、证据与 locator 关系建立材料维度索引。
 * 未被事实引用的材料保持“通用 / 待归类”，不根据文件名猜测业务归属。
 */
export function materialDimensionIndex(facts: FactVersion[], evidence: EvidenceReference[]) {
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  const index = new Map<string, Set<DimensionId>>();
  facts.forEach((fact) => fact.evidenceRefs.forEach((evidenceId) => {
    const materialId = evidenceById.get(evidenceId)?.locator?.materialId;
    if (!materialId) return;
    const dimensions = index.get(materialId) ?? new Set<DimensionId>();
    dimensions.add(fact.dimensionId);
    index.set(materialId, dimensions);
  }));
  return index;
}
