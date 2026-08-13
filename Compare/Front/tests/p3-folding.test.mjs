import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { DIMENSION_IDS } from "../src/contracts/workbench.ts";

const root = new URL("../", import.meta.url);

async function readSources() {
  return Promise.all([
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
}

test("P3-F1 uses one default-open registry for risk plus all six dimensions", async () => {
  const [review] = await readSources();

  assert.deepEqual(DIMENSION_IDS, ["compliance", "transaction", "production", "revenue", "debt", "cashflow"]);
  assert.equal(1 + DIMENSION_IDS.length, 7);
  assert.match(review, /REVIEW_SECTION_IDS: readonly ReviewSectionId\[\] = \["risk", \.\.\.DIMENSION_IDS\]/);
  assert.match(review, /useState<Set<ReviewSectionId>>\(\(\) => new Set\(REVIEW_SECTION_IDS\)\)/);
  assert.doesNotMatch(review, /收起全部明细|展开全部明细|review-fold-actions/);
  assert.match(review, /expanded=\{expandedSectionIds\.has\("risk"\)\}/);
  assert.match(review, /expanded=\{expandedSectionIds\.has\("compliance"\)\}/);
  assert.match(review, /expanded=\{expandedSectionIds\.has\(dimension\.id\)\}/);
});

test("P3-F1 keeps every section mounted behind one accessible summary toggle", async () => {
  const [review, detail] = await readSources();

  assert.match(detail, /aria-controls=\{bodyId\} aria-expanded=\{expanded\} aria-label=\{actionLabel\}/);
  assert.match(detail, /expanded \? `向上收起\$\{title\}明细` : `向下展开\$\{title\}明细`/);
  assert.match(detail, /data-review-section-toggle=\{sectionId\}/);
  assert.match(review, /sectionId="risk"/);
  assert.match(review, /sectionId="compliance"/);
  assert.match(detail, /sectionId=\{dimension\.id\}/);
  assert.match(review, /className="review-section-body" hidden=\{!sectionExpanded\} id="review-section-body-risk"/);
  assert.match(review, /className="review-section-body" hidden=\{!expanded\} id="review-section-body-compliance"/);
  assert.match(detail, /className="review-section-body" hidden=\{!expanded\} id=\{`review-section-body-\$\{dimension\.id\}`\}/);

  const autoOpenStart = review.indexOf("const dimensionId = selectedTarget?.dimensionId;");
  const autoOpenEnd = review.indexOf("}, [selectedTarget]);", autoOpenStart);
  assert.notEqual(autoOpenStart, -1);
  assert.notEqual(autoOpenEnd, -1);
  const autoOpen = review.slice(autoOpenStart, autoOpenEnd);
  assert.match(autoOpen, /if \(current\.has\(dimensionId\)\) return current/);
  assert.match(autoOpen, /next\.add\(dimensionId\)/);
  assert.doesNotMatch(autoOpen, /onEvidenceSelect|reviewTargetId|factVersionId|evidenceRef/);
});

test("P3-F1 preserves directional corner anchors and adapts content by container width", async () => {
  const [review, detail, styles] = await readSources();

  assert.match(review, /Expand review canvas from the upper-left corner[\s\S]*className="pane-corner-anchor review-corner-anchor"[\s\S]*pane-corner-glyph">↘/);
  assert.match(review, /Collapse review canvas to the upper-left corner[\s\S]*className="pane-corner-anchor review-corner-anchor"[\s\S]*pane-corner-glyph">↖/);
  for (const direction of ["right", "down", "left", "up"]) assert.match(styles, new RegExp(`\\.direction-${direction} svg`));
  for (const source of [review, detail, styles]) assert.doesNotMatch(source, /fullscreen/i);

  assert.match(styles, /\.review-canvas\s*\{[^}]*container:\s*review \/ inline-size/);
  assert.match(styles, /container-name:\s*review-section/);
  assert.match(styles, /@container review \(max-width:\s*720px\)/);
  assert.match(styles, /@container review-section \(max-width:\s*720px\)/);
  assert.match(styles, /@container review-section \(min-width:\s*1080px\)/);
  assert.match(styles, /\.review-section-body\[hidden\]\s*\{[^}]*display:\s*none !important/);
  assert.match(styles, /\.review-pane-heading\s*>\s*\.review-fold-actions\s*\{[^}]*display:\s*flex[^}]*flex-direction:\s*row[^}]*flex-wrap:\s*nowrap/);
  assert.doesNotMatch(styles, /\.review-fold-actions button span\s*\{[^}]*display:\s*none/);
  assert.match(styles, /\.dimension-section\.is-section-collapsed\s*\{[^}]*min-height:\s*0[^}]*padding-top:\s*4px[^}]*padding-bottom:\s*4px/);
  assert.match(styles, /\.dimension-section\.is-section-collapsed \.review-section-summary\s*\{[^}]*min-height:\s*34px/);
  assert.match(styles, /@container review-section \(max-width:\s*720px\)[\s\S]*?\.review-section-summary\s*\{[^}]*flex-direction:\s*row/);
  assert.match(styles, /\.review-section-summary-main p\s*\{[^}]*white-space:\s*nowrap/);
  assert.match(styles, /\.review-section-summary \.section-badges\s*\{[^}]*width:\s*auto/);
  assert.match(styles, /\.detail-table-row\s*\{[^}]*grid-template-columns:\s*minmax\(100px, \.72fr\) minmax\(0, 1\.28fr\)/);
  assert.match(styles, /\.dimension-information-board\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1\.75fr\) minmax\(250px, \.72fr\)/);
  assert.match(styles, /@media \(prefers-reduced-motion:\s*reduce\)[\s\S]*\.section-fold-toggle\s*\{[^}]*transition:\s*none/);
});
