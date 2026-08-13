import type { CSSProperties } from "react";
import type { DecisionGrade, DimensionDefinition, DimensionId } from "../contracts/workbench";
import { DIMENSION_IDS } from "../contracts/workbench";
import { GRADE_COLOR_VARS, scoreRadius, scoreToGrade } from "../lib/workbenchLogic";
import { copy, usePublicLocale } from "../lib/publicLocale";
import { dimensionColorVar, Icon } from "./icons";

function cssVars(values: Record<string, string | number>) {
  return values as CSSProperties;
}

export function normalizeCompactDimensions(dimensions: readonly DimensionDefinition[]) {
  const ids = dimensions.map((dimension) => dimension.id);
  const unique = new Set(ids);
  const valid = dimensions.length === DIMENSION_IDS.length
    && unique.size === DIMENSION_IDS.length
    && DIMENSION_IDS.every((id) => unique.has(id));

  if (!valid) {
    throw new Error("六维缩略图数据必须包含且仅包含合规、交易、生产、营收、负债、流水六个维度。");
  }

  return DIMENSION_IDS.map((id) => {
    const dimension = dimensions.find((item) => item.id === id);
    if (!dimension || !Number.isFinite(dimension.score) || dimension.score < 0 || dimension.score > 100) {
      throw new Error(`六维缩略图 ${id} 的分值无效。`);
    }
    return dimension;
  });
}

export function CompactDimensionDial({
  dimensions,
  decisionGrade,
  size = 92,
  className = "",
  variant = "default",
}: {
  dimensions: readonly DimensionDefinition[];
  decisionGrade: DecisionGrade;
  size?: number | string;
  className?: string;
  variant?: "default" | "thumbnail";
}) {
  const locale = usePublicLocale();
  let ordered: readonly DimensionDefinition[];
  try {
    ordered = normalizeCompactDimensions(dimensions);
  } catch (error) {
    if (process.env.NODE_ENV !== "production") throw error;
    return <div aria-label={copy(locale, "Invalid six-dimension thumbnail data", "六维缩略图数据异常")} className={`compact-dial-error ${className}`}>!</div>;
  }

  return (
    <div
      aria-label={copy(locale, `Six-dimension grade chart; the center color represents decision grade ${decisionGrade}`, `六维评级图，中心色为认定等级 ${decisionGrade}`)}
      className={`compact-dial${variant === "thumbnail" ? " compact-dial-thumbnail" : ""} ${className}`}
      role="img"
      style={cssVars({ "--compact-dial-size": typeof size === "number" ? `${size}px` : size })}
    >
      <div className="compact-dial-plot">
        {ordered.map((dimension, index) => (
          <div
            aria-hidden="true"
            className="compact-dial-sector"
            key={`sector-${dimension.id}`}
            style={cssVars({
              "--compact-sector-size": `${scoreRadius(dimension.score)}%`,
              "--compact-sector-color": GRADE_COLOR_VARS[scoreToGrade(dimension.score)],
              "--compact-rotation": `${index * 60}deg`,
            })}
          />
        ))}
        {ordered.map((dimension, index) => (
          <div
            aria-hidden="true"
            className="compact-dial-separator"
            key={`separator-${dimension.id}`}
            style={cssVars({ "--compact-rotation": `${index * 60 + 30}deg` })}
          />
        ))}
        <div aria-hidden="true" className="compact-dial-outline" />
        <div aria-hidden={variant === "thumbnail"} className="compact-dial-grade" style={cssVars({ "--compact-grade-color": GRADE_COLOR_VARS[decisionGrade] })}>
          {variant === "thumbnail" ? null : decisionGrade}
        </div>
      </div>
      {variant === "default" ? ordered.map((dimension, index) => (
        <span
          aria-hidden="true"
          className="compact-dial-icon"
          key={`icon-${dimension.id}`}
          style={cssVars({
            "--compact-icon-angle": `${index * 60}deg`,
            "--compact-icon-color": dimensionColorVar[dimension.id as DimensionId],
          })}
        >
          <Icon name={dimension.id} />
        </span>
      )) : null}
    </div>
  );
}
