import { MATERIAL_BUSINESS_FOLDERS } from "../contracts/workbench.ts";
import type { Material, MaterialBusinessFolder } from "../contracts/workbench.ts";

export type OriginalMaterial = Exclude<Material, { kind: "scene" }>;

export function isOriginalMaterial(material: Material): material is OriginalMaterial {
  if (material.role === "derived" || material.kind === "scene") return false;
  return material.kind !== "media" || material.mediaKind === "video";
}

function pathParts(material: Material) {
  return (material.businessPath ?? material.folderPath ?? "")
    .replaceAll("\\", "/")
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean);
}

export function businessFolderFor(material: OriginalMaterial): MaterialBusinessFolder {
  const explicit = pathParts(material).find((part): part is MaterialBusinessFolder => MATERIAL_BUSINESS_FOLDERS.includes(part as MaterialBusinessFolder));
  if (explicit) return explicit;
  const text = `${material.fileName} ${material.label}`.toLowerCase();
  if (/身份证|营业执照|证照|工商|法人|股东|registry|identity|license/u.test(text)) return "基本证照";
  if (/现场|厂门|厂区|车间|产线|工艺|原材料|在制|成品|铭牌|设备照片|site|factory|process|nameplate|equipment.*image/u.test(text)) return "现场照片";
  if (/租赁标的|设备合同|采购合同|销售合同|报价|invoice|quote|contract|financed.equipment/u.test(text)) return "租赁标的";
  if (/征信|房产|担保|抵押|负债|流水|credit|collateral|debt|cashflow|bank/u.test(text)) return "增信";
  return "经营证明";
}

export function materialRelativePath(material: OriginalMaterial) {
  const parts = pathParts(material);
  const folderIndex = parts.findIndex((part) => MATERIAL_BUSINESS_FOLDERS.includes(part as MaterialBusinessFolder));
  return folderIndex >= 0 && parts.length > folderIndex + 1 ? parts.slice(folderIndex + 1).join(" / ") : material.fileName;
}

export function materialPreviewUrl(material: Material) {
  // HTTP material records explicitly report archive availability. Never fall
  // back to a repository public URL when that controlled original is absent.
  if (material.originalAccess && !material.originalAccess.available) return undefined;
  if (material.originalUrl) return material.originalUrl;
  if (material.kind === "image" || material.kind === "media" || material.kind === "scene") return material.assetUrl;
  return undefined;
}
