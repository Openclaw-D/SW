import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

function parseArgs(argv) {
  const result = {};
  for (let index = 2; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || !value) throw new Error(`invalid argument near ${key ?? "<end>"}`);
    result[key.slice(2)] = value;
  }
  return result;
}

function columnName(index) {
  let value = index + 1;
  let name = "";
  while (value > 0) {
    value -= 1;
    name = String.fromCharCode(65 + (value % 26)) + name;
    value = Math.floor(value / 26);
  }
  return name;
}

function safeSheetName(name, used) {
  const base = String(name || "Sheet").replace(/[\\/?*:[\]]/gu, "_").slice(0, 31) || "Sheet";
  let candidate = base;
  let suffix = 2;
  while (used.has(candidate)) {
    candidate = `${base.slice(0, Math.max(1, 31 - String(suffix).length - 1))}-${suffix}`;
    suffix += 1;
  }
  used.add(candidate);
  return candidate;
}

function widthForColumn(columns, rows, index) {
  const values = [columns[index], ...rows.map((row) => row[index])];
  const longest = Math.max(...values.map((value) => String(value ?? "").length));
  return Math.min(30, Math.max(11, Math.ceil(longest * 1.15)));
}

function excelFormulaFor(columns, rowIndex, columnIndex) {
  const label = columns[columnIndex];
  const excelRow = rowIndex + 4;
  const find = (pattern) => columns.findIndex((value) => pattern.test(value));
  const cell = (index) => `${columnName(index)}${excelRow}`;
  const pairFormula = (leftPattern, rightPattern, operator) => {
    const left = find(leftPattern);
    const right = find(rightPattern);
    return left >= 0 && right >= 0 ? `=${cell(left)}${operator}${cell(right)}` : null;
  };
  if (/^净额/u.test(label)) return pairFormula(/^流入/u, /^流出/u, "-");
  if (/^合价/u.test(label)) return pairFormula(/^数量$/u, /^单价/u, "*");
  if (/^销项税额/u.test(label)) {
    const income = find(/^计税收入/u);
    return income >= 0 ? `=${cell(income)}*13%` : null;
  }
  if (/^税额/u.test(label)) {
    const amount = find(/^发票金额/u);
    return amount >= 0 ? `=${cell(amount)}*13%` : null;
  }
  if (/^电费/u.test(label)) {
    const power = find(/^用电量/u);
    return power >= 0 ? `=${cell(power)}*0.000078` : null;
  }
  if (/^所有者权益/u.test(label)) return pairFormula(/^资产总额/u, /^负债总额/u, "-");
  if (/^净利润/u.test(label)) return pairFormula(/^营业收入/u, /^营业成本及费用/u, "-");
  if (/^累计收入/u.test(label)) {
    const amount = find(/^确认收入/u);
    if (amount < 0) return null;
    return rowIndex === 0 ? `=${cell(amount)}` : `=${columnName(columnIndex)}${excelRow - 1}+${cell(amount)}`;
  }
  if (/^累计回款/u.test(label)) {
    const amount = find(/^回款金额/u);
    if (amount < 0) return null;
    return rowIndex === 0 ? `=${cell(amount)}` : `=${columnName(columnIndex)}${excelRow - 1}+${cell(amount)}`;
  }
  return null;
}

async function buildWorkbook(api, spec) {
  const { FileBlob, SpreadsheetFile, Workbook } = api;
  const workbook = Workbook.create();
  const usedNames = new Set();
  const builtSheetNames = [];
  for (const sourceSheet of spec.sheets) {
    const sheetName = safeSheetName(sourceSheet.name, usedNames);
    builtSheetNames.push(sheetName);
    const sheet = workbook.worksheets.add(sheetName);
    const columns = sourceSheet.columns.map((value) => String(value));
    const rows = sourceSheet.rows.map((row) => row.map((value) => value ?? null));
    const matrix = [columns, ...rows];
    const lastColumn = columnName(columns.length - 1);
    const lastRow = Math.max(4, rows.length + 3);
    sheet.getRange(`A1:${lastColumn}1`).merge();
    sheet.getRange("A1").values = [[spec.label]];
    sheet.getRange(`A2:${lastColumn}2`).merge();
    sheet.getRange("A2").values = [[`${spec.projectNo} · 完整脱敏模拟原始材料 · 非真实客户数据`]];
    const usedRange = sheet.getRange(`A3:${lastColumn}${lastRow}`);
    usedRange.values = matrix;
    rows.forEach((_, rowIndex) => {
      columns.forEach((__, columnIndex) => {
        const formula = excelFormulaFor(columns, rowIndex, columnIndex);
        if (formula) sheet.getCell(rowIndex + 3, columnIndex).formulas = [[formula]];
      });
    });
    usedRange.format = {
      borders: { preset: "all", style: "thin", color: "#D8DEE8" },
      font: { name: "Microsoft YaHei", size: 10, color: "#172033" },
      verticalAlignment: "center",
      wrapText: true,
    };
    sheet.getRange(`A1:${lastColumn}1`).format = {
      fill: "#0F172A",
      font: { name: "Microsoft YaHei", bold: true, color: "#FFFFFF", size: 14 },
      verticalAlignment: "center",
    };
    sheet.getRange(`A2:${lastColumn}2`).format = {
      fill: "#E8EEF7",
      font: { name: "Microsoft YaHei", color: "#475569", size: 9 },
      verticalAlignment: "center",
    };
    const header = sheet.getRange(`A3:${lastColumn}3`);
    header.format = {
      fill: "#162033",
      font: { name: "Microsoft YaHei", bold: true, color: "#FFFFFF", size: 10 },
      horizontalAlignment: "center",
      verticalAlignment: "center",
      wrapText: true,
    };
    header.format.rowHeight = 28;
    if (rows.length) {
      sheet.getRange(`A4:${lastColumn}${lastRow}`).format.rowHeight = 22;
      columns.forEach((label, columnIndex) => {
        const lower = label.toLowerCase();
        const range = sheet.getRange(`${columnName(columnIndex)}4:${columnName(columnIndex)}${lastRow}`);
        if (/金额|收入|负债|流入|流出|净额|能力|本金|利息|租金|单价|合价|产量|用电/u.test(label)) {
          range.format.numberFormat = "#,##0.00";
        } else if (/比例|比率|利用率|份额|成数/u.test(label) || /ratio|rate/u.test(lower)) {
          range.format.numberFormat = "0.00";
        }
      });
    }
    columns.forEach((_, columnIndex) => {
      sheet.getRange(`${columnName(columnIndex)}1:${columnName(columnIndex)}${lastRow}`).format.columnWidth = widthForColumn(columns, rows, columnIndex);
    });
    sheet.getRange(`A1:${lastColumn}1`).format.rowHeight = 32;
    sheet.getRange(`A2:${lastColumn}2`).format.rowHeight = 22;
    sheet.freezePanes.freezeRows(3);
    sheet.showGridLines = false;
  }
  const audit = workbook.worksheets.add(safeSheetName("勾稽摘要", usedNames));
  const auditRows = [["项目编号", spec.projectNo], ["材料名称", spec.label], ["数据状态", "完整脱敏模拟 · synthetic_demo"], ["工作表数量", spec.sheets.length]];
  audit.getRange("A1:B1").merge();
  audit.getRange("A1").values = [["COMPARE · 勾稽与定位摘要"]];
  audit.getRange("A2:B2").values = [["核验字段", "结果 / 来源"]];
  audit.getRange(`A3:B${auditRows.length + 2}`).values = auditRows;
  audit.getRange("A1:B1").format = { fill: "#0F172A", font: { name: "Microsoft YaHei", bold: true, color: "#FFFFFF", size: 14 }, verticalAlignment: "center" };
  audit.getRange("A2:B2").format = { fill: "#162033", font: { name: "Microsoft YaHei", bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
  audit.getRange(`A2:B${auditRows.length + 2}`).format = { borders: { preset: "all", style: "thin", color: "#D8DEE8" }, font: { name: "Microsoft YaHei", size: 10 }, verticalAlignment: "center", wrapText: true };
  audit.getRange("A1:B1").format.rowHeight = 32;
  audit.getRange("A1:A20").format.columnWidth = 22;
  audit.getRange("B1:B20").format.columnWidth = 54;
  audit.getRange("A3:A20").format.fill = "#F8FAFC";
  audit.getRange("A8:B8").values = [["公式：工作表记录总数", null]];
  const rowCountTerms = spec.sheets.map((sourceSheet) => {
    const name = safeSheetName(sourceSheet.name, new Set());
    const finalRow = Math.max(4, sourceSheet.rows.length + 3);
    return `COUNTA('${name.replace(/'/gu, "''")}'!A4:A${finalRow})`;
  });
  audit.getRange("B8").formulas = [[`=${rowCountTerms.join("+") || "0"}`]];
  audit.getRange("A9:B9").values = [["业务路径", spec.businessPath ?? "未声明"]];
  audit.getRange("A10:B10").values = [["定位说明", "各原始工作表冻结前三行；A3 起为字段表头，可按 sheet/range 定位。"]];
  audit.getRange("A11:B11").merge();
  audit.getRange("A11").values = [["本工作簿仅用于 P5 本地演示和单项目勾稽，不代表真实客户、真实交易或统计验证结论。"]];
  audit.getRange("A11:B11").format = { fill: "#FEF3C7", font: { name: "Microsoft YaHei", color: "#92400E", size: 9 }, wrapText: true, verticalAlignment: "center" };
  audit.getRange("A11:B11").format.rowHeight = 32;
  audit.freezePanes.freezeRows(2);
  audit.showGridLines = false;
  await fs.mkdir(path.dirname(spec.outputPath), { recursive: true });
  const output = await api.SpreadsheetFile.exportXlsx(workbook);
  await output.save(spec.outputPath);

  const imported = await SpreadsheetFile.importXlsx(await FileBlob.load(spec.outputPath));
  const inspection = await imported.inspect({ kind: "sheet,formula", maxChars: 3000, options: { maxResults: 100 } });
  if (/#[A-Z0-9/?!]+/u.test(inspection.ndjson ?? "")) {
    throw new Error(`formula error detected in ${spec.outputPath}`);
  }
  for (const suffix of [".inspect.ndjson", ".inspect.ndjson.jsonl", ".ndjson"]) {
    await fs.rm(`${spec.outputPath}${suffix}`, { force: true });
  }
  if (spec.renderDir) {
    await fs.mkdir(spec.renderDir, { recursive: true });
    for (const sheetName of [...builtSheetNames, "勾稽摘要"]) {
      const preview = await imported.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
      const safeName = sheetName.replace(/[\\/?*:[\]]/gu, "_");
      await fs.writeFile(path.join(spec.renderDir, `${safeName}.png`), new Uint8Array(await preview.arrayBuffer()));
    }
  }
}

const args = parseArgs(process.argv);
if (!args.spec || !args["artifact-tool"]) {
  throw new Error("usage: node build_native_workbooks.mjs --spec <json> --artifact-tool <module path>");
}
const moduleUrl = args["artifact-tool"].startsWith("file:")
  ? args["artifact-tool"]
  : pathToFileURL(path.resolve(args["artifact-tool"])).href;
const api = await import(moduleUrl);
const payload = JSON.parse(await fs.readFile(path.resolve(args.spec), "utf8"));
let completed = 0;
for (const spec of payload.workbooks) {
  await buildWorkbook(api, spec);
  completed += 1;
  if (completed % 24 === 0 || completed === payload.workbooks.length) {
    process.stdout.write(`built ${completed}/${payload.workbooks.length} workbooks\n`);
  }
}
