export function dialState(index: number, hoveredIndex: number | null, activeIndex: number) {
  // 风险是总览，不是第七维：选中风险时仍完整展示六维的真实评分颜色。
  if (hoveredIndex === null) return activeIndex < 0 ? "" : index === activeIndex ? "is-current" : "is-dimmed";
  return index === hoveredIndex ? "is-hovered" : "is-dimmed";
}
