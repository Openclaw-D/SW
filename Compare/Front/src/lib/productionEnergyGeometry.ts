import type { TimeGrain } from "../contracts/workbench";

export type ProductionEnergyDisplayGrain = TimeGrain | "quarter";

export const PRODUCTION_ENERGY_SLOT_WIDTH = 56;
export const PRODUCTION_ENERGY_LABEL_SPACING = 84;

export function productionEnergyPlotGeometry(pointCount: number, grain: ProductionEnergyDisplayGrain) {
  const safePointCount = Math.max(0, Math.floor(pointCount));
  const slotWidth = PRODUCTION_ENERGY_SLOT_WIDTH;
  const minimumPlotWidth = Math.max(slotWidth, safePointCount * slotWidth);
  const periodCenterPercent = (index: number) => safePointCount > 0 ? (index + .5) / safePointCount * 100 : 50;
  const lineCenters = Array.from({ length: safePointCount }, (_, index) => periodCenterPercent(index));
  const labelEvery = Math.max(1, Math.ceil(PRODUCTION_ENERGY_LABEL_SPACING / slotWidth));
  return { grain, slotWidth, minimumPlotWidth, periodCenterPercent, lineCenters, labelEvery };
}

export function productionEnergyEvidenceUnion(primaryEvidenceRefs: string[], secondaryEvidenceRefs: string[]) {
  return [...new Set([...primaryEvidenceRefs, ...secondaryEvidenceRefs].filter(Boolean))];
}
