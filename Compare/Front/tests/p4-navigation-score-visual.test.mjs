import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { DIMENSION_IDS } from "../src/contracts/workbench.ts";
import {
  deriveScoreVisual,
  GRADE_COLOR_VARS,
  normalizeScore,
  scoreRadius,
  scoreToGrade,
} from "../src/lib/workbenchLogic.ts";
import { dialState } from "../src/lib/navigationRailState.ts";

const root = new URL("../", import.meta.url);

test("P4 normalizes score once for grade, five-color, dial radius and bar progress", () => {
  const boundaries = [
    [0, "E"],
    [19.9, "E"],
    [20, "D"],
    [39.9, "D"],
    [40, "C"],
    [59.9, "C"],
    [60, "B"],
    [79.9, "B"],
    [80, "A"],
    [100, "A"],
  ];

  for (const [score, grade] of boundaries) {
    const visual = deriveScoreVisual(score);
    assert.deepEqual(visual, {
      normalizedScore: score,
      grade,
      colorVar: GRADE_COLOR_VARS[grade],
      radiusPercent: scoreRadius(score),
      progressPercent: score,
    });
    assert.equal(scoreToGrade(score), grade);
  }

  assert.equal(normalizeScore(79.94), 79.9);
  assert.equal(normalizeScore(79.95), 80);
  assert.equal(deriveScoreVisual(79.94).grade, "B");
  assert.deepEqual(deriveScoreVisual(79.95), {
    normalizedScore: 80,
    grade: "A",
    colorVar: "var(--grade-a)",
    radiusPercent: scoreRadius(80),
    progressPercent: 80,
  });
});

test("P4 gives all six navigation dimensions one shared score visual contract", () => {
  const scores = [0, 20, 40, 60, 80, 100];
  const visuals = DIMENSION_IDS.map((id, index) => ({ id, ...deriveScoreVisual(scores[index]) }));

  assert.equal(visuals.length, 6);
  assert.deepEqual(visuals.map(({ grade }) => grade), ["E", "D", "C", "B", "A", "A"]);
  assert.deepEqual(visuals.map(({ progressPercent }) => progressPercent), scores);
  assert.deepEqual(visuals.map(({ colorVar }) => colorVar), [
    "var(--grade-e)",
    "var(--grade-d)",
    "var(--grade-c)",
    "var(--grade-b)",
    "var(--grade-a)",
    "var(--grade-a)",
  ]);
  assert.equal(visuals.every(({ normalizedScore, grade, colorVar, radiusPercent, progressPercent }) => {
    const source = deriveScoreVisual(normalizedScore);
    return grade === source.grade
      && colorVar === source.colorVar
      && radiusPercent === source.radiusPercent
      && progressPercent === source.progressPercent;
  }), true);
});

test("P4 risk overview keeps every dial sector visible while a dimension selection still dims its peers", () => {
  assert.equal(dialState(0, null, -1), "");
  assert.equal(dialState(5, null, -1), "");
  assert.equal(dialState(2, null, 2), "is-current");
  assert.equal(dialState(1, null, 2), "is-dimmed");
});

test("P4 NavigationRail consumes one visual object for sectors, icons, bars and labels", async () => {
  const [navigation, styles, tokens] = await Promise.all([
    readFile(new URL("src/components/NavigationRail.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
    readFile(new URL("src/styles/tokens.css", root), "utf8"),
  ]);

  assert.match(navigation, /const navigationItems = dimensions\.map\([\s\S]*visual: deriveScoreVisual\(dimension\.score\)/);
  assert.match(navigation, /--sector-size": `\$\{visual\.radiusPercent\}%`/);
  assert.match(navigation, /--sector-color": visual\.colorVar/);
  assert.match(navigation, /className=\{`axis-icon-anchor[\s\S]*--score-color": visual\.colorVar[\s\S]*className="dimension-axis-icon"/);
  assert.match(navigation, /className=\{`dimension-entry[\s\S]*--score-color": visual\.colorVar[\s\S]*--score-progress": `\$\{visual\.progressPercent\}%`/);
  assert.match(navigation, /className="dimension-grade">\{visual\.grade\}/);
  assert.doesNotMatch(navigation, /dimensionColorVar|--dimension-color|--material-(?:confirmed|review|conflict)/);

  assert.match(styles, /\.dimension-entry\s*\{[\s\S]*var\(--score-color\)[\s\S]*var\(--score-progress\)/);
  assert.match(styles, /\.dimension-entry svg\s*\{[^}]*color:\s*var\(--score-color\)/);
  assert.match(styles, /\.dimension-grade\s*\{[^}]*color:\s*var\(--score-color\)/);
  assert.match(styles, /\.dimension-axis-icon\s*\{[^}]*color:\s*var\(--score-color\)/);
  assert.match(styles, /#navigation-rail :is\(\.wedge-hit, \.dial-score, \.risk-nav-entry, \.dimension-entry\):focus\s*\{[^}]*outline:\s*2px solid var\(--color-focus\)/);
  assert.doesNotMatch(navigation, /dimension-dial-grade|grade-ribbon/);
  assert.ok(navigation.indexOf('className="mini-navigation-card"') < navigation.indexOf('六维综合评分等级'));
  assert.ok(navigation.indexOf('aria-label="风险与六维栏目"') < navigation.indexOf('六维综合评分等级'));
  assert.ok(navigation.indexOf('六维综合评分等级') < navigation.indexOf('className={`dimension-entry'));
  assert.match(navigation, /className="risk-grade">\{overallVisual\.grade\}/);
  assert.match(navigation, /--score-progress": `\$\{overallVisual\.progressPercent\}%`/);
  assert.match(navigation, /const riskNavigationIndex = 0/);
  assert.match(navigation, /aria-label=\{copy\(locale, `\$\{riskNavigationIndex\} Risk; \$\{riskItemCount\} items/);
  assert.match(navigation, /className=\{`risk-nav-entry \$\{listState\(riskActive\)\}`\}/);
  assert.match(navigation, /className=\{`dimension-entry \$\{listState\(!riskActive && dimension\.id === activeId\)\}`\}/);
  assert.match(styles, /\.dimension-entry\.is-dimmed,[\s\S]*?\.risk-nav-entry\.is-dimmed \{ opacity:\s*\.42/);
  assert.match(styles, /\.mini-navigation-card \{[^}]*min-height:\s*156px[^}]*margin-top:\s*-8px/);
  assert.match(styles, /\.dial-stage \{ width:\s*164px; height:\s*156px/);
  assert.match(styles, /\.detail-dial-stage \{ transform:\s*translateY\(-4px\); \}/);
  assert.doesNotMatch(navigation, /置顶|riskLevel/);

  for (const [grade, color] of [["a", "#22c55e"], ["b", "#2563eb"], ["c", "#f59e0b"], ["d", "#dc2626"], ["e", "#7c3aed"]]) {
    assert.match(tokens, new RegExp(`--grade-${grade}: ${color}`));
  }
  for (const materialToken of ["--material-confirmed", "--material-review", "--material-conflict"]) {
    assert.match(tokens, new RegExp(`${materialToken}:`));
    assert.doesNotMatch(navigation, new RegExp(materialToken));
  }
});
