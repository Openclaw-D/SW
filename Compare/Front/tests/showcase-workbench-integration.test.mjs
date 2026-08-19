import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const root = new URL("../", import.meta.url);
const read = (file) => readFile(new URL(file, root), "utf8");

test("showcase pre-review stays gated and follows the single-row presentation architecture", async () => {
  const [app, review, topbar, navigation, materialPane, css, preReviewCss, collaborationPanel] = await Promise.all([
    read("src/App.tsx"),
    read("src/components/ReviewCanvas.tsx"),
    read("src/components/TopBar.tsx"),
    read("src/components/NavigationRail.tsx"),
    read("src/components/MaterialPane.tsx"),
    read("src/styles/app.css"),
    read("src/styles/pre-review.css"),
    read("src/components/A2ACollaborationPanel.tsx"),
  ]);

  assert.match(app, /const preReviewEnabled = showSimulationControls/);
  assert.match(app, /setPreReviewState\(preReviewEnabled \? createPreReviewDemoState\(projectId\) : null\)/);
  assert.match(app, /\[gateway, projectId, preReviewEnabled, presentationMode\]/);
  assert.match(app, /centerContent=\{preReviewEnabled && preReviewState \? <PreReviewSummaryBar/);
  assert.match(app, /actionContent=\{preReviewEnabled && preReviewState \? <PreReviewActionBar/);
  assert.match(app, /leadingContent=\{presentationMode \? <div className="topbar-dial">/);
  assert.match(app, /\{presentationMode \? null : <NavigationRail/);
  assert.match(app, /presentationMode=\{presentationMode\}/);
  assert.match(app, /is-presentation-layout/);
  assert.match(app, /presentationTargetForDimension/);
  assert.match(app, /void selectEvidenceGroup\(presentationTarget\)/);
  assert.match(app, /<div className=\{`workbench-app \$\{presentationMode \? "is-presentation-workbench" : ""\}`\}/);
  assert.doesNotMatch(app, /PreReviewPanel/);
  assert.match(app, /riskSection\.tabIndex = -1; riskSection\.focus\(\)/);
  assert.match(app, /scrollReviewElementIntoView\(riskSection\)/);
  assert.doesNotMatch(app, /scrollIntoView/);
  assert.doesNotMatch(app, /gateway\.(?:run|save|submit)PreReview/);

  assert.match(topbar, /centerContent \? <div className="topbar-center-content">\{centerContent\}<\/div>/);
  assert.match(topbar, /\{actionContent\}/);
  assert.doesNotMatch(review, /preReviewPanel/);
  assert.match(review, /riskChangeSummary\?: string \| null/);
  assert.match(review, /className="risk-change-note"/);
  assert.match(topbar, /!presentationMode \? <div className="topbar-controls">/);
  assert.doesNotMatch(css, /\.showcase-banner\s*\{/);
  assert.match(css, /\.showcase-experience\s*\{[^}]*height:\s*100dvh[^}]*overflow-x:\s*hidden/s);
  assert.match(css, /\.workbench-app\s*\{[\s\S]*grid-template-rows:\s*var\(--layout-topbar-height\)\s+minmax\(0, 1fr\)/);
  assert.doesNotMatch(css, /has-pre-review-summary/);
  assert.match(css, /\.topbar-center-content \{ width: min\(60vw, 980px\); position: absolute;/);
  assert.match(css, /grid-template-columns: minmax\(180px, 20fr\) minmax\(0, 80fr\);/);
  assert.match(css, /\.showcase-experience \.pre-review-summary__bar,[\s\S]*\.workbench-app\.is-presentation-workbench \.pre-review-summary__bar \{ width: 33\.333vw; grid-column: 4; grid-row: 1; justify-self: end; \}/);
  assert.match(css, /\.workbench-body\.has-embedded-chat\.is-presentation-layout/);
  assert.match(css, /\.workbench-body\.has-embedded-chat\.is-presentation-layout\.is-middle-collapsed:not\(\.is-material-collapsed\) \{[\s\S]*grid-template-columns: 0 minmax\(0, 1fr\) 0 0;/);
  assert.match(css, /\.navigation-rail\.is-presentation-map/);
  assert.match(css, /\.material-pane\.is-context-preview \.material-tabs \{ display: none; \}/);
  assert.match(css, /\.material-pane\.is-context-preview\.is-directory-open \.material-tabs/);
  assert.match(preReviewCss, /pre-review-segment--deny/);
  assert.match(preReviewCss, /\.pre-review-segment \{[\s\S]*min-width: 5%;[\s\S]*grid-template-rows: repeat\(2, auto\);/);
  assert.match(preReviewCss, /\.pre-review-segment--deny \{ color: #991b1b; background: #fee2e2; \}/);
  assert.doesNotMatch(preReviewCss, /pre-review-dimension-table/);
  assert.match(css, /#review-risk \.risk-level-forbid \{ --risk-group-color: #7c3aed; \}/);
  assert.match(css, /risk-level-card:is\(\.risk-level-forbid, \.risk-level-risk, \.risk-level-confirm\)/);
  assert.match(css, /risk-level-detail:is\(\.risk-level-forbid, \.risk-level-risk, \.risk-level-confirm\) \.risk-row/);
  assert.match(collaborationPanel, /当前选中依据 · \{selectionLabel\}/);
  assert.match(navigation, /presentationMode \? "showcase-dimension-tags" : "dimension-list"/);
  assert.match(navigation, /!presentationMode \? <button/);
  assert.match(css, /\.topbar-dial \.navigation-rail\.is-presentation-map \.dial \{ width: 60px; height: 60px; overflow: hidden; border-radius: 50%; background: var\(--color-surface\); \}/);
  assert.match(css, /\.topbar-dial \.navigation-rail\.is-presentation-map \.axis-icon-anchor,[\s\S]*\.topbar-dial \.showcase-dimension-tags \{ display: none; \}/);
  assert.match(preReviewCss, /\.pre-review-top-actions button \{ min-width: 64px; min-height: 42px;/);
  assert.match(preReviewCss, /\.showcase-experience \.pre-review-summary \{ height: 100%; gap: 0; \}/);
  assert.match(preReviewCss, /\.showcase-experience \.pre-review-segment \{ height: 100%; border-right: 1px dashed #cbd0d8; \}/);
  assert.match(preReviewCss, /\.showcase-experience \.pre-review-top-actions button \{[\s\S]*flex: 1 1 0;/);
  assert.match(materialPane, /presentationMode \? "对比材料" : "原始材料"/);
  assert.match(materialPane, /showPresentationDirectory \? "关闭原件" : "查看原件"/);
  assert.match(materialPane, /aria-label="收起对比材料至右上角"/);
  assert.match(materialPane, /presentationMode \? "从右上角展开对比材料"/);
  assert.match(materialPane, /presentationMode \? null : <MaterialIntelligencePanel/);
  const summary = await read("src/components/PreReviewSummaryBar.tsx");
  assert.match(summary, /trafficLightTendencySegments/);
  assert.doesNotMatch(summary, /background: "#dbeafe"/);
  assert.match(summary, /复核: \{ background: "#fef3c7", color: "#78350f" \}/);
  assert.match(summary, /否决: \{ background: "#fee2e2", color: "#991b1b" \}/);
  assert.match(summary, /const version = state\.status === "not_started" \? "V0"/);
  assert.match(summary, /const runLabel = state\.status === "not_started" \? "开始预审"/);
  assert.match(summary, />差异<\/button>/);
  assert.match(summary, /pre-review-version-dot/);
  assert.match(summary, /estimateRingPresentation/);
  assert.match(summary, /pre-review-estimate-ring/);
  assert.doesNotMatch(summary, /<i aria-hidden/);
  assert.match(summary, />提交<\/button>/);
  assert.doesNotMatch(summary, />退回<\/button>/);
  assert.match(summary, />提交<\/button>[\s\S]*>复核<\/button>[\s\S]*>否决<\/button>/);
  assert.match(summary, />复核<\/button>/);
  assert.match(summary, />否决<\/button>/);
  assert.doesNotMatch(summary, /查看风险/);
});
