import { useState } from "react";
import type { CSSProperties } from "react";
import type { DimensionDefinition, DimensionId } from "../contracts/workbench";
import { dialState } from "../lib/navigationRailState";
import { copy, formatDimensionName, usePublicLocale } from "../lib/publicLocale";
import { averageScore, deriveScoreVisual } from "../lib/workbenchLogic";
import { Icon } from "./icons";
import { Button } from "./ui";

const scoreRingSizes = [100, 80, 60, 40, 20].map((score) => deriveScoreVisual(score).radiusPercent);
const riskNavigationIndex = 0;

function cssVars(values: Record<string, string | number>) {
  return values as CSSProperties;
}

function listState(isActive: boolean) {
  return isActive ? "is-active" : "is-dimmed";
}

export function NavigationRail({
  dimensions,
  activeId,
  collapsed,
  riskActive,
  riskItemCount,
  onNavigate,
  onRiskNavigate,
  onOverview,
  onToggleCollapsed,
}: {
  dimensions: DimensionDefinition[];
  activeId: DimensionId;
  collapsed: boolean;
  riskActive: boolean;
  riskItemCount: number;
  onNavigate: (id: DimensionId) => void;
  onRiskNavigate: () => void;
  onOverview: () => void;
  onToggleCollapsed: () => void;
}) {
  const locale = usePublicLocale();
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const activeIndex = riskActive ? -1 : dimensions.findIndex((dimension) => dimension.id === activeId);
  const overallScore = averageScore(dimensions.map((dimension) => dimension.score));
  const overallVisual = deriveScoreVisual(overallScore);
  const navigationItems = dimensions.map((dimension) => ({
    dimension,
    visual: deriveScoreVisual(dimension.score),
  }));

  return (
    <aside className={`navigation-rail ${collapsed ? "is-collapsed" : ""}`} aria-label={copy(locale, "Six-dimension navigation", "六维导航")} data-semantic-localized id="navigation-rail">
      <div className="navigation-toolbar">
        <Button
          aria-controls="navigation-rail"
          aria-expanded={!collapsed}
          aria-label={collapsed ? copy(locale, "Expand six-dimension navigation to the right", "向右展开六维导航") : copy(locale, "Collapse six-dimension navigation to the left", "向左折叠六维导航")}
          onClick={onToggleCollapsed}
          title={collapsed ? copy(locale, "Expand navigation to the right", "向右展开导航") : copy(locale, "Collapse navigation to the left", "向左折叠导航")}
        >
          <Icon name="chevron" />
        </Button>
      </div>

      {!collapsed ? (
        <section className="mini-navigation-card" aria-label={copy(locale, "Six-dimension quick navigation", "六维快捷导航")}>
          <div className="dial-stage detail-dial-stage">
            <div className="dial">
              {navigationItems.map(({ dimension }, index) => (
                <div
                  aria-hidden="true"
                  className={`direction-corridor ${dialState(index, hoveredIndex, activeIndex)}`}
                  key={`corridor-${dimension.id}`}
                  onMouseEnter={() => setHoveredIndex(index)}
                  onMouseLeave={() => setHoveredIndex(null)}
                  style={cssVars({ "--rotation": `${index * 60}deg` })}
                />
              ))}

              {navigationItems.map(({ dimension, visual }, index) => (
                <div
                  aria-hidden="true"
                  className={`sector-color ${dialState(index, hoveredIndex, activeIndex)}`}
                  data-grade={visual.grade}
                  data-score={visual.normalizedScore}
                  key={`sector-${dimension.id}`}
                  style={cssVars({
                    "--sector-size": `${visual.radiusPercent}%`,
                    "--sector-color": visual.colorVar,
                    "--rotation": `${index * 60}deg`,
                  })}
                />
              ))}

              {scoreRingSizes.map((size) => (
                <div
                  aria-hidden="true"
                  className="score-ring"
                  key={size}
                  style={cssVars({ "--ring-size": `${size}%` })}
                />
              ))}

              {navigationItems.map(({ dimension }, index) => (
                <div
                  aria-hidden="true"
                  className="dimension-separator"
                  key={`separator-${dimension.id}`}
                  style={cssVars({ "--rotation": `${index * 60 + 30}deg` })}
                />
              ))}

              <div className="dial-outline" aria-hidden="true" />

              {navigationItems.map(({ dimension, visual }, index) => (
                <button
                  aria-current={!riskActive && dimension.id === activeId ? "page" : undefined}
                  aria-label={copy(locale, `Go to ${formatDimensionName(dimension.id, locale, dimension.fullName)}; score grade ${visual.grade}`, `定位到${dimension.fullName}，评级 ${visual.grade}`)}
                  className={`wedge-hit ${dialState(index, hoveredIndex, activeIndex)}`}
                  key={`hit-${dimension.id}`}
                  onBlur={() => setHoveredIndex(null)}
                  onClick={() => onNavigate(dimension.id)}
                  onFocus={() => setHoveredIndex(index)}
                  onMouseEnter={() => setHoveredIndex(index)}
                  onMouseLeave={() => setHoveredIndex(null)}
                  style={cssVars({ "--rotation": `${index * 60}deg` })}
                  type="button"
                />
              ))}

              <button
                aria-label={copy(locale, `Return to the six-dimension overview; overall score grade ${overallVisual.grade}`, `返回六维总览，综合评分等级 ${overallVisual.grade}`)}
                aria-current={riskActive ? "page" : undefined}
                className={`dial-score detail-dial-back ${riskActive ? "is-overview" : ""}`}
                onClick={onOverview}
                style={cssVars({ "--score-color": overallVisual.colorVar })}
                type="button"
              >
                {overallVisual.grade}
              </button>
            </div>

            {navigationItems.map(({ dimension, visual }, index) => (
              <div
                aria-hidden="true"
                className={`axis-icon-anchor ${dialState(index, hoveredIndex, activeIndex)}`}
                data-grade={visual.grade}
                data-score={visual.normalizedScore}
                key={`icon-${dimension.id}`}
                style={cssVars({
                  "--icon-angle": `${index * 60}deg`,
                  "--score-color": visual.colorVar,
                })}
              >
                <span className="dimension-axis-icon"><Icon name={dimension.id} /></span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <nav className="dimension-list" aria-label={copy(locale, "Risk and six-dimension sections", "风险与六维栏目")}>
        <button
          aria-current={riskActive ? "page" : undefined}
          aria-label={copy(locale, `${riskNavigationIndex} Risk; ${riskItemCount} items; overall score grade ${overallVisual.grade}`, `${riskNavigationIndex} 风险，共 ${riskItemCount} 项，六维综合评分等级 ${overallVisual.grade}`)}
          className={`risk-nav-entry ${listState(riskActive)}`}
          data-grade={overallVisual.grade}
          data-score={overallVisual.normalizedScore}
          onClick={onRiskNavigate}
          style={cssVars({
            "--score-color": overallVisual.colorVar,
            "--score-progress": `${overallVisual.progressPercent}%`,
          })}
          type="button"
        >
          <Icon name="risk" />
          {!collapsed ? <><b className="risk-index">{riskNavigationIndex}</b><span>{copy(locale, "Risk", "风险")}</span><b className="risk-grade">{overallVisual.grade}</b></> : null}
        </button>
        {navigationItems.map(({ dimension, visual }) => (
          <button
            aria-current={!riskActive && dimension.id === activeId ? "page" : undefined}
            aria-label={copy(locale, `${dimension.index} ${formatDimensionName(dimension.id, locale, dimension.name)}; score grade ${visual.grade}`, `${dimension.index} ${dimension.name}，评级 ${visual.grade}`)}
            className={`dimension-entry ${listState(!riskActive && dimension.id === activeId)}`}
            data-grade={visual.grade}
            data-score={visual.normalizedScore}
            key={dimension.id}
            onClick={() => onNavigate(dimension.id)}
            style={cssVars({
              "--score-color": visual.colorVar,
              "--score-progress": `${visual.progressPercent}%`,
            })}
            type="button"
          >
            <Icon name={dimension.id} />
            {!collapsed ? (
              <>
                <b className="dimension-index">{dimension.index}</b>
                <span className="dimension-name">{formatDimensionName(dimension.id, locale, dimension.name)}</span>
                <span aria-hidden="true" className="dimension-grade">{visual.grade}</span>
              </>
            ) : null}
          </button>
        ))}
      </nav>
    </aside>
  );
}
