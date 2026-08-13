import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { DIMENSION_IDS } from "../src/contracts/workbench.ts";
import { MockWorkbenchGateway } from "../src/gateway/mockWorkbenchGateway.ts";
import { materialDimensionIndex } from "../src/lib/materialIndex.ts";
import { mockWorkbenchProject } from "../src/mock/mockCase.ts";
import {
  deriveSimulatedRiskLevel,
  generateProjectCatalog,
  groupProjectValue,
  projectRiskBand,
} from "../src/mock/projectCatalog.ts";
import { averageScore, displayIndustryName, INDUSTRY_DISPLAY_ORDER, scoreToGrade } from "../src/lib/workbenchLogic.ts";

const root = new URL("../", import.meta.url);
const fixedDate = new Date(2026, 7, 8, 12, 0, 0);

test("所有页面使用统一的两字行业展示名，底层行业值保持不变", () => {
  assert.deepEqual(INDUSTRY_DISPLAY_ORDER.map(displayIndustryName), ["金属", "注塑", "纺织", "印包", "玻璃", "电子"]);
  assert.equal(displayIndustryName("未配置行业"), "未配置行业");
});

test("项目目录生成 24 个当日唯一项目，并在六个行业中均分", () => {
  const projects = generateProjectCatalog(101, fixedDate);
  assert.equal(projects.length, 24);
  assert.equal(new Set(projects.map((project) => project.projectId)).size, 24);
  assert.ok(projects.every((project) => /^2026PAZL0808\d{3}$/.test(project.projectId)));

  const industryCounts = Object.values(Object.groupBy(projects, (project) => project.industry)).map((items) => items?.length);
  assert.deepEqual(industryCounts, [4, 4, 4, 4, 4, 4]);
  assert.ok(projects.every((project) => project.isSimulated && project.financingType === "设备融资"));
  assert.ok(projects.every((project) => project.riskBand === projectRiskBand(project.riskLevel)));
  assert.ok(projects.every((project) => project.riskLevel === "confirm" && project.riskBand === "核实"));
});

test("每个项目都严格保持 Compare 固定六维顺序，缩略图只使用评级", () => {
  const projects = generateProjectCatalog(202, fixedDate);
  projects.forEach((project) => {
    assert.deepEqual(project.dimensions.map((dimension) => dimension.id), DIMENSION_IDS);
    assert.match(project.decisionGrade, /^[A-E]$/);
  });
});

test("目录 fixture 生成器对日期稳定，并允许显式 seed 构造独立测试样本", () => {
  const first = generateProjectCatalog(301, fixedDate);
  const second = generateProjectCatalog(302, fixedDate);
  assert.deepEqual(first.map((project) => project.projectId), second.map((project) => project.projectId));
  assert.notDeepEqual(
    first.map((project) => [project.durationDays, project.amountWan, project.decisionGrade]),
    second.map((project) => [project.durationDays, project.amountWan, project.decisionGrade]),
  );
});

test("默认 Mock Gateway 返回固定 24 项，不随实例或当前时间重新生成", async () => {
  const first = await new MockWorkbenchGateway().listProjects();
  const second = await new MockWorkbenchGateway().listProjects();

  assert.deepEqual(first, second);
  assert.equal(first.length, 24);
  assert.ok(first.every((project) => /^2026PAZL0812\d{3}$/.test(project.projectId)));
});

test("分组值覆盖行业、风险、时间、区域和门店五种认定方式", () => {
  const [project] = generateProjectCatalog(404, fixedDate);
  assert.equal(groupProjectValue(project, "industry"), project.industry);
  assert.equal(groupProjectValue(project, "risk"), project.riskBand);
  assert.equal(groupProjectValue(project, "time"), project.timeBucket);
  assert.equal(groupProjectValue(project, "region"), project.region);
  assert.equal(groupProjectValue(project, "store"), project.store);
});

test("当前统一模板的材料状态、置信度与 decisionGrade 单独变化均不降低 confirm 风险", () => {
  const [project] = generateProjectCatalog(414, fixedDate);
  const changedDecision = { ...project, decisionGrade: project.decisionGrade === "A" ? "E" : "A" };
  const highConfidence = project.dimensions.map((dimension) => ({ ...dimension, confidence: 90 }));
  const lowConfidence = project.dimensions.map((dimension) => ({ ...dimension, confidence: 60 }));

  assert.equal(groupProjectValue(changedDecision, "risk"), project.riskBand);
  assert.equal(changedDecision.riskLevel, project.riskLevel);
  assert.equal(changedDecision.riskBand, projectRiskBand(changedDecision.riskLevel));
  assert.equal(deriveSimulatedRiskLevel(project.dimensions, "待补材料"), "confirm");
  assert.equal(deriveSimulatedRiskLevel(project.dimensions, "人工复核"), "confirm");
  assert.equal(deriveSimulatedRiskLevel(highConfidence, "材料齐备"), "confirm");
  assert.equal(deriveSimulatedRiskLevel(lowConfidence, "材料齐备"), "confirm");
  assert.notEqual(changedDecision.decisionGrade, project.decisionGrade);
});

test("Compare Gateway 把清单中的同一项目 ID 和六维数据交给工作台", async () => {
  const projects = generateProjectCatalog(505, fixedDate);
  const gateway = new MockWorkbenchGateway(505, projects);
  const catalog = await gateway.listProjects();
  const selected = catalog[7];
  const workbench = await gateway.loadProject(selected.projectId);

  assert.equal(workbench.project.id, selected.projectId);
  assert.match(workbench.project.name, new RegExp(selected.companyShortName));
  assert.deepEqual(workbench.dimensions, selected.dimensions);
  assert.equal(workbench.riskSummary.decisionGrade, selected.decisionGrade);
  assert.equal(workbench.riskSummary.level, selected.riskLevel);
  assert.match(workbench.riskSummary.summary, new RegExp(`风险级别：${selected.riskBand}`));
  assert.match(workbench.riskSummary.summary, new RegExp(`材料状态：${selected.materialStatus}`));
  assert.match(workbench.riskSummary.summary, new RegExp(`决策等级：${selected.decisionGrade}`));
  assert.ok(workbench.reviewEvents.every((event) => event.projectId === selected.projectId));
});

test("评分、审批、置信、五级风险与 hard gate 五项保持独立", async () => {
  const projects = generateProjectCatalog(515, fixedDate);
  const selectedIndex = 5;
  const dimensionScores = [35, 88, 67, 54, 72, 91];
  projects[selectedIndex] = {
    ...projects[selectedIndex],
    decisionGrade: "A",
    riskLevel: "confirm",
    riskBand: projectRiskBand("confirm"),
    dimensions: projects[selectedIndex].dimensions.map((dimension, index) => ({
      ...dimension,
      score: dimensionScores[index],
      scoreGrade: scoreToGrade(dimensionScores[index]),
      confidence: 41 + index * 3,
    })),
  };
  const selected = projects[selectedIndex];
  const gateway = new MockWorkbenchGateway(515, projects);
  const workbench = await gateway.loadProject(selected.projectId);
  const templateDeterminations = new Map(mockWorkbenchProject.determinations.map((item) => [item.dimensionId, item]));

  assert.equal(workbench.riskSummary.scoreGrade, scoreToGrade(averageScore(dimensionScores)));
  assert.equal(workbench.riskSummary.decisionGrade, "A");
  assert.equal(workbench.riskSummary.confidence, 49);
  assert.equal(workbench.riskSummary.level, "confirm");
  assert.ok(workbench.riskSummary.hardConstraintResults.some((rule) => rule.gateTriggered));
  assert.deepEqual(
    workbench.riskSummary.hardConstraintResults.map((rule) => [rule.id, rule.gateTriggered]),
    mockWorkbenchProject.riskSummary.hardConstraintResults.map((rule) => [rule.id, rule.gateTriggered]),
  );

  workbench.determinations.forEach((determination) => {
    const dimension = selected.dimensions.find((item) => item.id === determination.dimensionId);
    const template = templateDeterminations.get(determination.dimensionId);
    assert.equal(determination.score, dimension?.score);
    assert.equal(determination.scoreGrade, dimension?.scoreGrade);
    assert.equal(determination.decisionGrade, template?.decisionGrade);
    assert.deepEqual(
      determination.hardConstraintResults.map((rule) => [rule.id, rule.gateTriggered]),
      template?.hardConstraintResults.map((rule) => [rule.id, rule.gateTriggered]),
    );
  });
  assert.ok(workbench.determinations.some((determination) => determination.decisionGrade !== "A"));
});

test("详情全局风险不低于当前最严重风险项和人工 hard gate 语义", async () => {
  const projects = generateProjectCatalog(525, fixedDate);
  const gateway = new MockWorkbenchGateway(525, projects);
  const workbench = await gateway.loadProject(projects[3].projectId);
  const severity = { support: 0, attention: 1, confirm: 2, risk: 3, forbid: 4 };
  const itemLevels = [
    ...workbench.riskSummary.keyAnomalies.map((item) => item.level),
    ...workbench.riskSummary.pendingHumanDeterminations.map((item) => item.level),
    ...workbench.riskSummary.hardConstraintResults
      .filter((rule) => rule.gateTriggered)
      .map((rule) => rule.result === "block" ? "forbid" : "confirm"),
  ];
  const mostSevereActualLevel = Math.max(...itemLevels.map((level) => severity[level]));

  assert.equal(workbench.riskSummary.level, "confirm");
  assert.ok(severity[workbench.riskSummary.level] >= mostSevereActualLevel);
});

test("非基础项目会确定性替换统一模板中的全部项目身份，同时保持证据关系稳定", async () => {
  const projects = generateProjectCatalog(606, fixedDate);
  const gateway = new MockWorkbenchGateway(606, projects);
  const selected = projects[11];
  const workbench = await gateway.loadProject(selected.projectId);
  const materials = await gateway.listMaterials(selected.projectId);
  const serialized = JSON.stringify(workbench);
  const borrower = workbench.complianceGraph.nodes.find((node) => node.role === "承租主体");

  assert.equal(workbench.project.id, selected.projectId);
  assert.equal(borrower?.name, selected.companyName);
  assert.match(workbench.project.name, /统一脱敏核验模板/);
  assert.match(workbench.project.disclaimer, /不代表 24 套真实客户材料/);
  assert.ok(workbench.complianceGraph.nodes.some((node) => node.name === `${selected.companyShortName}控股有限公司`));
  assert.equal(workbench.complianceGraph.nodes.every((node) => !node.name.includes("（演示）")), true);
  assert.ok(workbench.materials.some((material) => JSON.stringify(material).includes(selected.companyName)));
  assert.ok(materials.some((material) => JSON.stringify(material).includes(selected.companyName)));
  assert.doesNotMatch(JSON.stringify(materials), /华东精密制造有限公司|华东控股有限公司|华东精密设备融资/);
  const productionDetail = workbench.dimensionDetails.find((detail) => detail.dimensionId === "production");
  assert.ok(productionDetail);
  assert.doesNotMatch(JSON.stringify(productionDetail), /华东精密|精密制造/);
  assert.doesNotMatch(serialized, /华东精密制造有限公司|华东控股有限公司|华东精密设备融资/);

  assert.deepEqual(workbench.evidence.map((item) => item.id), mockWorkbenchProject.evidence.map((item) => item.id));
  assert.deepEqual(workbench.evidence.map((item) => item.locator), mockWorkbenchProject.evidence.map((item) => item.locator));
  assert.deepEqual(workbench.facts.map((item) => item.id), mockWorkbenchProject.facts.map((item) => item.id));
  assert.deepEqual(workbench.facts.map((item) => item.evidenceRefs), mockWorkbenchProject.facts.map((item) => item.evidenceRefs));
});

test("多次读取同一项目不会共享可变引用", async () => {
  const projects = generateProjectCatalog(707, fixedDate);
  const gateway = new MockWorkbenchGateway(707, projects);
  const selected = projects[19];
  const first = await gateway.loadProject(selected.projectId);
  const second = await gateway.loadProject(selected.projectId);

  first.project.name = "被外部修改";
  first.complianceGraph.nodes[0].name = "被外部修改";
  first.dimensions[0].score = 0;

  assert.notStrictEqual(first, second);
  assert.notEqual(second.project.name, "被外部修改");
  assert.equal(second.complianceGraph.nodes.find((node) => node.role === "承租主体")?.name, selected.companyName);
  assert.deepEqual(second.dimensions, selected.dimensions);
});

test("根入口属于 Compare，工作台不再硬编码旧演示项目", async () => {
  const [page, experience, selection, app, dial, css, materialPane, appCss, eye] = await Promise.all([
    readFile(new URL("app/page.tsx", root), "utf8"),
    readFile(new URL("src/ProjectExperience.tsx", root), "utf8"),
    readFile(new URL("src/components/ProjectSelection.tsx", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/CompactDimensionDial.tsx", root), "utf8"),
    readFile(new URL("src/styles/project-selection.css", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
    readFile(new URL("public/demo-eye.png", root)),
  ]);

  assert.match(page, /<ProjectExperience \/>/);
  assert.match(experience, /<DemoEntrance locale=\{locale\} onEnter=/);
  assert.match(experience, /<ProjectSelectionEntry/);
  assert.match(experience, /<ProjectSelectionBrowser/);
  assert.match(experience, /screen: "demo"/);
  assert.match(experience, /nextProjects\.length !== 24/);
  assert.doesNotMatch(experience, /sessionStorage|Math\.random|serializeProjectCatalog|parseProjectCatalog/);
  assert.doesNotMatch(selection, /换一批|onRefresh/);
  assert.match(selection, /Enter public demo/);
  assert.match(selection, /Public demo — no authentication is performed/);
  assert.match(selection, /24 isolated projects share a complete/);
  assert.match(selection, /src="\/demo-eye\.png"/);
  assert.ok(eye.byteLength > 1_000_000);
  assert.match(css, /filter:\s*brightness\(\.36\) saturate\(\.68\)/);
  assert.match(css, /object-position:\s*50% 50%/);
  assert.match(css, /\.demo-entrance-action:focus-visible/);
  assert.match(materialPane, /按业务维度筛选材料/);
  assert.match(materialPane, /按材料类型筛选材料/);
  assert.match(materialPane, /保留当前/);
  assert.match(appCss, /\.material-tab-list\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill,\s*minmax\(132px,\s*1fr\)\)[^}]*overflow-y:\s*auto/);
  assert.doesNotMatch(selection, /<p>选择模式<\/p>/);
  assert.doesNotMatch(selection, /24 个演示项目/);
  assert.match(selection, /<EntryPreview locale=\{locale\} projects=\{projects\} view=\{view\} \/>/);
  assert.match(selection, /const ENTRY_PREVIEW_COUNT = 6/);
  assert.equal(selection.match(/previewProjects\(projects, ENTRY_PREVIEW_COUNT\)/g)?.length, 2);
  assert.equal(selection.match(/slice\(0, ENTRY_PREVIEW_COUNT\)/g)?.length, 2);
  assert.match(selection, /count-\$\{groupItems\.length\}/);
  assert.doesNotMatch(selection, /items\.slice\(0, 2\)/);
  assert.match(selection, /copy\(locale, "No\.", "序号"\)[\s\S]*copy\(locale, "Grade", "评级"\)[\s\S]*copy\(locale, "Company", "企业名称"\)[\s\S]*copy\(locale, "Amount", "金额"\)[\s\S]*copy\(locale, "Industry", "行业"\)/);
  assert.match(selection, /entry-preview-sequence">\{index \+ 1\}/);
  assert.match(selection, /amountWan \/ 5000 \* 100/);
  assert.match(selection, /entry-preview-amount/);
  assert.match(selection, /<IndustryProcessIcon industry=\{project\.industry\}/);
  assert.match(selection, /formatProjectIndustry\(project\.industry, locale\)/);
  assert.match(selection, /displayIndustryName\(industry\)/);
  assert.match(selection, /projectGroupLabel\(group\.label, groupBasis, locale\)/);
  assert.doesNotMatch(selection, />\{project\.industry\}</);
  assert.doesNotMatch(selection, /<b>\{industry\}<\/b>/);
  assert.match(selection, /entry-preview-company/);
  assert.match(selection, /entry-preview-duration/);
  assert.match(selection, /durationDays <= 7 \? 25 : durationDays <= 15 \? 50 : durationDays <= 30 \? 75 : 100/);
  assert.equal(selection.match(/<ProjectCardIndicators (?:compact )?locale=\{locale\} project=\{project\} \/>/g)?.length, 2);
  assert.match(selection, /className="project-card-amount-indicator"/);
  assert.match(selection, /className="project-card-industry-indicator"/);
  assert.match(selection, /className="project-card-duration-indicator"/);
  assert.match(selection, /<small>\{copy\(locale, "Status", "状态"\)\}<\/small>/);
  assert.doesNotMatch(selection, /<small>时长<\/small>|<MetaPair label="材料"/);
  assert.match(selection, /MATERIAL_PREVIEW_LABELS\[project\.materialStatus\]/);
  assert.doesNotMatch(selection, /entry-preview-check/);
  assert.doesNotMatch(selection, /previewProjects\(projects, 8\)/);
  assert.doesNotMatch(selection, /entry-option-index|entry-option-action|进入\{PROJECT_VIEW_LABELS|const descriptions/);
  assert.match(app, /gateway\.loadProject\(projectId, \{ signal: controller\.signal \}\)/);
  assert.doesNotMatch(app, /MOCK_PROJECT_ID/);
  assert.match(dial, /DIMENSION_IDS\.map/);
  assert.doesNotMatch(dial, /levelMarks|grade-ribbon|A、B、C、D、E/);
  assert.equal(selection.match(/variant="thumbnail"/g)?.length, 6);
  assert.match(dial, /variant\?: "default" \| "thumbnail"/);
  assert.match(dial, /variant === "default" \? ordered\.map/);
  assert.match(dial, /variant === "thumbnail" \? null : decisionGrade/);
  assert.match(selection, /querySelectorAll<HTMLElement>\("\.entry-option-heading"\)/);
  assert.match(selection, /heading\.animate\(\[/);
  assert.match(selection, /window\.setTimeout\(\(\) => onChoose\(view\), 420\)/);
  assert.match(selection, /prefers-reduced-motion: reduce/);
  assert.doesNotMatch(selection, /<span>排序<\/span><select/);
  assert.match(selection, /const SORT_METRICS = \["decisionGrade", "amountWan", "durationDays", "createdAt"\]/);
  assert.match(selection, /setSortDirection\(\(current\) => current === "asc" \? "desc" : "asc"\)/);
  assert.match(selection, /aria-label=\{copy\(locale, "Project metrics", "项目指标"\)\}/);
  assert.match(selection, /aria-label=\{copy\(locale, "Grouping dimensions", "分组指标"\)\}/);
  assert.match(selection, /copy\(locale, "Company", "企业名称"\)[\s\S]*sortMetricControl\("amountWan", "is-list-head"\)[\s\S]*sortMetricControl\("durationDays", "is-list-head"\)[\s\S]*copy\(locale, "Industry", "行业"\)[\s\S]*copy\(locale, "Region", "区域"\)[\s\S]*copy\(locale, "Salesperson", "业务员"\)[\s\S]*copy\(locale, "Status", "状态"\)/);
  assert.match(selection, /project-list-company"><b>\{projectCompany\(project, locale\)\}<\/b><small>\{project\.projectNo\}<\/small><\/span>/);
  assert.match(selection, /project-list-region"><b>\{formatProjectRegion\(project\.region, locale\)\}<\/b><small>\{formatProjectStore\(project\.store, locale\)\}<\/small>/);
  assert.match(selection, /project-list-salesperson"><b>\{formatProjectSalesperson\(project\.salesperson, locale\)\}<\/b>/);
  assert.match(selection, /project-list-status"><b className=\{`material-state/);
  assert.doesNotMatch(selection, /\{project\.region\} · \{project\.salesperson\}/);
});

test("材料索引只从现有事实、证据与 locator 派生业务维度", async () => {
  const gateway = new MockWorkbenchGateway();
  const [catalogItem] = await gateway.listProjects();
  const project = await gateway.loadProject(catalogItem.projectId);
  const index = materialDimensionIndex(project.facts, project.evidence);

  assert.ok(index.size > 0);
  for (const [materialId, dimensions] of index) {
    assert.ok(project.materials.some((material) => material.id === materialId));
    assert.ok([...dimensions].every((dimensionId) => DIMENSION_IDS.includes(dimensionId)));
  }
});

test("项目入口与内部视图共用清晰指标，分组画布使用更充足的双向空间", async () => {
  const css = await readFile(new URL("src/styles/project-selection.css", root), "utf8");
  const minimumTwelvePixelSelectors = [
    ".project-list-head",
    ".project-card-top",
    ".project-group-circle > header span",
    ".project-group-items button span",
    ".project-group-items button small",
    ".selection-browser-footer",
    ".project-number",
  ];

  minimumTwelvePixelSelectors.forEach((selector) => {
    const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    assert.match(css, new RegExp(`${escapedSelector}[^}]*font-size:\\s*12px`), selector);
  });

  assert.match(css, /\.selection-entry-grid\s*\{[^}]*width:\s*min\(96%,\s*1800px\)[^}]*height:\s*min\(92%,\s*900px\)/);
  assert.match(css, /\.selection-content\s*\{[^}]*padding:\s*26px 36px 48px/);
  assert.match(css, /\.project-list-row\s*\{[^}]*grid-template-columns:\s*52px 84px minmax\(205px,\s*300px\) minmax\(140px,\s*210px\) 106px/);
  assert.match(css, /\.project-list-duration\s*\{[^}]*place-items:\s*center/);
  assert.match(css, /\.project-card-indicators\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\) 38px 38px 70px/);
  assert.match(css, /\.project-group-grid\s*\{[^}]*minmax\(min\(100%,\s*360px\),\s*1fr\)/);
  assert.match(css, /\.project-group-circle\s*\{[^}]*width:\s*min\(100%,\s*390px\)/);
  assert.match(css, /\.project-group-items\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*112px\)[^}]*justify-content:\s*center[^}]*gap:\s*28px 12px/);
  assert.match(css, /\.project-group-items button\s*\{[^}]*width:\s*112px[^}]*grid-template:\s*64px auto auto \/ minmax\(0,\s*1fr\)/);
  assert.match(css, /\.project-group-items button span\s*\{[^}]*overflow-wrap:\s*anywhere/);
  assert.doesNotMatch(css, /\.project-group-items button span\s*\{[^}]*text-overflow:\s*ellipsis/);
});
