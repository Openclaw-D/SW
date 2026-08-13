import type {
  DimensionSeriesGroup,
  EvidenceReference,
  FactVersion,
  FinancedEquipmentLedger,
  Material,
  OperatingEquipmentStatus,
  ProductionEnergySeries,
  ProductionStage,
  PublicReferenceImage,
  TransactionRepaymentSchedule,
} from "../contracts/workbench";

const simulatedSource = "脱敏模拟合同、报价与运营记录；不代表真实客户或市场报价";

function benchmarkMedian(line: FinancedEquipmentLedger["lines"][number]) {
  return line.priceBenchmark.status === "available" ? line.priceBenchmark.median : null;
}

export const mockReferenceImages: PublicReferenceImage[] = [
  {
    id: "reference-equipment-tsugami",
    category: "equipment",
    src: "/reference-images/equipment-tsugami-lathe.jpg",
    title: "Tsugami CNC 车床",
    description: "融资设备类别的公开示意照片，用于帮助理解设备外形。",
    author: "Whoisjohngalt",
    originUrl: "https://commons.wikimedia.org/wiki/File:Tsugami_CNC_Lathe.jpg",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0/",
    usage: "融资设备公开参考图",
    isEvidence: false,
  },
  {
    id: "reference-equipment-mori",
    category: "equipment",
    src: "/reference-images/equipment-mori-vmc.jpg",
    title: "Mori Seiki 立式加工中心",
    description: "加工中心类别的公开示意照片，不对应本项目设备铭牌或序列号。",
    author: "EvasiveMobile",
    originUrl: "https://commons.wikimedia.org/wiki/File:Mori_Seiki_FM-1.jpg",
    license: "CC0 1.0",
    licenseUrl: "https://creativecommons.org/publicdomain/zero/1.0/",
    usage: "融资设备公开参考图",
    isEvidence: false,
  },
  {
    id: "reference-raw-bars",
    category: "raw-material",
    src: "/reference-images/raw-bar-stock.jpg",
    title: "金属棒材原料",
    description: "公开的金属棒材参考照片，用于表达生产流程中的原材料阶段。",
    author: "Alister 77",
    originUrl: "https://commons.wikimedia.org/wiki/File:Assorted_bar_stock.jpg",
    license: "Public domain",
    licenseUrl: "https://creativecommons.org/publicdomain/mark/1.0/",
    usage: "生产原材料阶段参考图",
    isEvidence: false,
  },
  {
    id: "reference-process-cnc",
    category: "process",
    src: "/reference-images/process-cnc-milling.jpg",
    title: "CNC 铣削工艺",
    description: "公开的 CNC 加工过程照片，用于表达机加工步骤。",
    author: "Impressionmanufacturer",
    originUrl: "https://commons.wikimedia.org/wiki/File:CNC_milling_machine.jpg",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0/",
    usage: "生产工艺阶段参考图",
    isEvidence: false,
  },
  {
    id: "reference-process-suzhou",
    category: "process",
    src: "/reference-images/process-suzhou-machining.jpg",
    title: "苏州精密金属加工场景",
    description: "公开发布的中国大陆精密金属加工参考照片。",
    author: "Leadingtopunion",
    originUrl: "https://commons.wikimedia.org/wiki/File:Precision_metal_machining_and_welding_for_heavy_industrial_components.jpg",
    license: "CC0 1.0",
    licenseUrl: "https://creativecommons.org/publicdomain/zero/1.0/",
    usage: "生产工艺阶段参考图",
    isEvidence: false,
  },
  {
    id: "reference-finished-nidelok",
    category: "finished-product",
    src: "/reference-images/finished-cncmilled-parts.png",
    title: "CNC 铣削金属零件",
    description: "公开的铝与钢制精密加工零件照片，用于表达成品阶段。",
    author: "NideloK",
    originUrl: "https://commons.wikimedia.org/wiki/File:Aluminum_and_steel_parts_made_with_CNC_milling_machine_in_NideloK.png",
    license: "CC0 1.0",
    licenseUrl: "https://creativecommons.org/publicdomain/zero/1.0/",
    usage: "生产成品阶段参考图",
    isEvidence: false,
  },
  {
    id: "reference-finished-lampin",
    category: "finished-product",
    src: "/reference-images/finished-lampin-components.jpg",
    title: "精密机加工组件",
    description: "公开的精密机加工组件照片，用于成品图集补充。",
    author: "Whoisjohngalt",
    originUrl: "https://commons.wikimedia.org/wiki/File:Lampin_Machined_Components.jpg",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0/",
    usage: "生产成品阶段参考图",
    isEvidence: false,
  },
];

const transactionRentTotal = 2_096_100;

export const mockTransactionRepaymentSchedule: TransactionRepaymentSchedule = {
  status: "available",
  termMonths: 36,
  amountUnit: "元",
  points: Array.from({ length: 36 }, (_, index) => {
    const principal = 54_800;
    const interest = 6_400 - index * 170;
    return {
      id: `transaction-rent-period-${String(index + 1).padStart(2, "0")}`,
      period: index + 1,
      principal,
      interest,
      rent: principal + interest,
      evidenceRefs: [`evidence-transaction-rent-period-${String(index + 1).padStart(2, "0")}-inputs`],
      isSimulated: true,
    };
  }),
  firstPaymentEvidenceRefs: ["evidence-transaction-rent-first"],
  firstTwelveEvidenceRefs: ["evidence-transaction-rent-first-12"],
  totalRentEvidenceRefs: ["evidence-transaction-rent-total"],
  termEvidenceRefs: ["evidence-transaction-rent-term"],
  message: "36期本金与利息按模拟融资方案逐期列示；每期租金等于本金与利息之和。",
  sourceLabel: "脱敏模拟融资方案与租金计划",
  isSimulated: true,
};

export const mockFinancedEquipment: FinancedEquipmentLedger = {
  currency: "CNY",
  amountUnit: "元",
  transactionStructure: "direct-lease",
  lessor: "演示融资租赁有限公司",
  termMonths: 36,
  downPaymentAmount: 767_200,
  financingPlanEvidenceRefs: ["evidence-transaction-plan"],
  projectAmountEvidenceRefs: ["evidence-transaction-project-amount"],
  financingRatioEvidenceRefs: ["evidence-transaction-finance-ratio-inputs"],
  partyRelationshipEvidenceRefs: ["evidence-transaction-relations"],
  totalContractEvidenceRefs: ["evidence-financed-total-contract"],
  repaymentSchedule: mockTransactionRepaymentSchedule,
  sourceLabel: simulatedSource,
  isSimulated: true,
  lines: [
    {
      id: "financed-equipment-1",
      equipment: "CNC 精密自动车床",
      brand: "津上",
      model: "M08SY",
      quantity: 2,
      contractUnitPrice: 410_000,
      supplier: "苏州精工设备有限公司",
      supplierRating: "A级",
      supplierRatingEvidenceRefs: ["evidence-financed-supplier-rating-1"],
      brandRating: "A级",
      brandRatingEvidenceRefs: ["evidence-financed-brand-rating-1"],
      contractQuoteSource: "模拟设备合同 C-2026-081",
      supplierQuoteSource: "模拟供应商报价 Q-2026-081",
      imageId: "reference-equipment-tsugami",
      modelPreset: { kind: "turning-center", width: 2.4, height: 1.8, depth: 1.9, spindleCount: 2, axisCount: 8, accent: "#7c93b2" },
      priceBenchmark: { status: "available", priceBasis: "per_unit", low: 370_000, median: 395_000, high: 430_000, sampleLabel: "同配置模拟可比区间", message: "同为单台、含税设备价口径。", unit: "元/台", sourceLabel: "脱敏模拟同配置价格基准表", factVersionId: "fact-price-benchmark-1-v1", evidenceRefs: ["evidence-financed-comparison-1"] },
      configuration: { status: "available", message: "配置口径已对齐", rows: [
        { id: "config-1-axis", factVersionId: "fact-config-1-axis-v1", label: "控制轴数", unit: "轴", current: "8 轴", median: "7 轴", range: "6–9 轴", sourceLabel: "脱敏模拟配置对比表", tone: "positive", evidenceRefs: ["evidence-financed-config-1-axis"] },
        { id: "config-1-spindle", factVersionId: "fact-config-1-spindle-v1", label: "主轴转速", unit: "rpm", current: "6000 rpm", median: "5500 rpm", range: "5000–6500 rpm", sourceLabel: "脱敏模拟配置对比表", tone: "neutral", evidenceRefs: ["evidence-financed-config-1-spindle"] },
      ] },
      contractEvidenceRefs: ["evidence-financed-contract-1"],
      supplierQuoteEvidenceRefs: ["evidence-financed-supplier-1"],
    },
    {
      id: "financed-equipment-2",
      equipment: "数控走心机",
      brand: "斯大",
      model: "SB-20R",
      quantity: 3,
      contractUnitPrice: 380_000,
      supplier: "常州精密机床有限公司",
      supplierRating: "B级",
      supplierRatingEvidenceRefs: ["evidence-financed-supplier-rating-2"],
      brandRating: "B级",
      brandRatingEvidenceRefs: ["evidence-financed-brand-rating-2"],
      contractQuoteSource: "模拟设备合同 C-2026-094",
      supplierQuoteSource: "模拟供应商报价 Q-2026-094",
      imageId: "reference-equipment-tsugami",
      modelPreset: { kind: "sliding-head-lathe", width: 2.1, height: 1.7, depth: 1.55, spindleCount: 2, axisCount: 7, accent: "#8097b1" },
      priceBenchmark: { status: "available", priceBasis: "per_unit", low: 350_000, median: 365_000, high: 390_000, sampleLabel: "同配置模拟可比区间", message: "同为单台、含税设备价口径。", unit: "元/台", sourceLabel: "脱敏模拟同配置价格基准表", factVersionId: "fact-price-benchmark-2-v1", evidenceRefs: ["evidence-financed-comparison-2"] },
      configuration: { status: "available", message: "配置口径已对齐", rows: [
        { id: "config-2-diameter", factVersionId: "fact-config-2-diameter-v1", label: "最大棒径", unit: "mm", current: "20 mm", median: "20 mm", range: "16–25 mm", sourceLabel: "脱敏模拟配置对比表", tone: "neutral", evidenceRefs: ["evidence-financed-config-2-diameter"] },
        { id: "config-2-spindle", factVersionId: "fact-config-2-spindle-v1", label: "主轴数量", unit: "个", current: "2", median: "2", range: "1–2", sourceLabel: "脱敏模拟配置对比表", tone: "positive", evidenceRefs: ["evidence-financed-config-2-spindle"] },
      ] },
      contractEvidenceRefs: ["evidence-financed-contract-2"],
      supplierQuoteEvidenceRefs: ["evidence-financed-supplier-2"],
    },
    {
      id: "financed-equipment-3",
      equipment: "数控加工中心",
      brand: "华锐",
      model: "VMC-850",
      quantity: 3,
      contractUnitPrice: 260_000,
      supplier: "华锐机电有限公司",
      supplierRating: "B级",
      supplierRatingEvidenceRefs: ["evidence-financed-supplier-rating-3"],
      brandRating: "B级",
      brandRatingEvidenceRefs: ["evidence-financed-brand-rating-3"],
      contractQuoteSource: "模拟设备合同 C-2026-102",
      supplierQuoteSource: "模拟供应商报价 Q-2026-102",
      imageId: "reference-equipment-mori",
      modelPreset: { kind: "machining-center", width: 2.6, height: 2.4, depth: 2.25, spindleCount: 1, axisCount: 3, accent: "#7590ad" },
      priceBenchmark: { status: "available", priceBasis: "per_unit", low: 245_000, median: 252_000, high: 275_000, sampleLabel: "同配置模拟可比区间", message: "同为单台、含税设备价口径。", unit: "元/台", sourceLabel: "脱敏模拟同配置价格基准表", factVersionId: "fact-price-benchmark-3-v1", evidenceRefs: ["evidence-financed-comparison-3"] },
      configuration: { status: "available", message: "配置口径已对齐", rows: [
        { id: "config-3-travel", factVersionId: "fact-config-3-travel-v1", label: "X 轴行程", unit: "mm", current: "850 mm", median: "800 mm", range: "750–900 mm", sourceLabel: "脱敏模拟配置对比表", tone: "positive", evidenceRefs: ["evidence-financed-config-3-travel"] },
        { id: "config-3-tools", factVersionId: "fact-config-3-tools-v1", label: "刀库容量", unit: "把", current: "24 把", median: "24 把", range: "20–30 把", sourceLabel: "脱敏模拟配置对比表", tone: "neutral", evidenceRefs: ["evidence-financed-config-3-tools"] },
      ] },
      contractEvidenceRefs: ["evidence-financed-contract-3"],
      supplierQuoteEvidenceRefs: ["evidence-financed-supplier-3"],
    },
  ],
};

export const mockOperatingEquipment: OperatingEquipmentStatus[] = [
  { id: "operating-equipment-turning", equipment: "精密自动车床", model: "多型号运营池", operatingQuantity: 5, status: "operating", utilization: "78%", ratedCapacity: "12,000 件/月", processUse: "车削与钻孔", evidenceRefs: ["evidence-operating-equipment-1"], sourceLabel: simulatedSource, isSimulated: true },
  { id: "operating-equipment-machining", equipment: "立式加工中心", model: "VMC 系列", operatingQuantity: 3, status: "maintenance", utilization: "64%", ratedCapacity: "7,200 件/月", processUse: "铣削与精加工", evidenceRefs: ["evidence-operating-equipment-2"], sourceLabel: simulatedSource, isSimulated: true },
];

export const mockProductionStages: ProductionStage[] = [
  { id: "production-stage-raw", stage: "raw-material", title: "金属棒材入库", summary: "按材质、炉批与规格完成入库核对。", fields: [{ label: "材质", value: "不锈钢 / 铝合金" }, { label: "核验", value: "炉批与规格" }], imageIds: ["reference-raw-bars"], evidenceRefs: ["evidence-production-stage-raw"], sourceLabel: simulatedSource, isSimulated: true },
  { id: "production-stage-process", stage: "process", title: "车削与精密机加工", summary: "车削、铣削、钻孔与质量检验按工艺卡流转。", fields: [{ label: "工序", value: "4 道" }, { label: "质检", value: "抽检 + 终检" }], imageIds: ["reference-process-suzhou", "reference-process-cnc"], evidenceRefs: ["evidence-production-stage-process"], sourceLabel: simulatedSource, isSimulated: true },
  { id: "production-stage-finished", stage: "finished-product", title: "精密零件成品入库", summary: "成品按批次完成尺寸、外观与包装记录。", fields: [{ label: "类别", value: "精密金属零件" }, { label: "状态", value: "批次入库" }], imageIds: ["reference-finished-nidelok", "reference-finished-lampin"], evidenceRefs: ["evidence-production-stage-finished"], sourceLabel: simulatedSource, isSimulated: true },
];

export const mockProductionEnergy: ProductionEnergySeries = {
  status: "available",
  electricityMetric: "usage",
  electricityUnit: "kWh",
  outputMetric: "absolute",
  outputUnit: "件",
  aggregation: "sum",
  message: "月度用电量与完工产量使用各自绝对值；不把产量环比混入同一轴。",
  sourceLabel: "脱敏模拟月度电表与完工记录；日期、单位和证据引用完整",
  isSimulated: true,
  points: [
    ["2026-01-01", "1月", 18_400, 10_800],
    ["2026-02-01", "2月", 17_600, 10_100],
    ["2026-03-01", "3月", 19_300, 11_450],
    ["2026-04-01", "4月", 20_100, 11_980],
    ["2026-05-01", "5月", 21_500, 12_760],
    ["2026-06-01", "6月", 20_900, 12_410],
  ].map(([date, label, electricity, output], index) => ({
    id: `production-energy-${index + 1}`,
    date: String(date),
    label: String(label),
    electricity: Number(electricity),
    output: Number(output),
    electricityEvidenceRefs: [`evidence-production-electricity-${index + 1}`],
    outputEvidenceRefs: [`evidence-production-output-${index + 1}`],
    isSimulated: true as const,
  })),
};

export const mockProductionPayrollSeries: DimensionSeriesGroup = {
  id: "production-payroll",
  label: "人员工资",
  points: [
    ["2026-04", "4月", 22.8, 38],
    ["2026-05", "5月", 23.2, 38],
    ["2026-06", "6月", 23.6, 38],
  ].map(([period, label, payroll, staff]) => {
    const payrollValue = Number(payroll);
    const staffValue = Number(staff);
    return {
      id: `production-payroll-${period}`,
      label: String(label),
      note: "工资总额与月末在岗人数；人均工资由两项输入确定性派生",
      measures: [
        { id: `production-payroll-${period}-amount`, label: "工资总额", value: payrollValue, unit: "万元", evidenceRefs: [`evidence-production-payroll-${period}-amount`] },
        { id: `production-payroll-${period}-staff`, label: "在岗人数", value: staffValue, unit: "人", evidenceRefs: [`evidence-production-payroll-${period}-staff`] },
        { id: `production-payroll-${period}-per-capita`, label: "人均工资", value: Number((payrollValue / staffValue).toFixed(2)), unit: "万元/人/月", evidenceRefs: [`evidence-production-payroll-${period}-per-capita-inputs`] },
      ],
    };
  }),
};

export const mockP2Materials: Material[] = [
  {
    id: "material-financed-equipment",
    versionId: "material-financed-equipment-v1",
    kind: "excel",
    fileName: "设备合价.xlsx",
    label: "融资设备合同与报价",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    availability: "available",
    isSimulated: true,
    sourceLabel: "脱敏模拟合同、供应商报价与可比价；仅用于交易审查",
    sheets: [
      {
        name: "合同设备",
        columns: ["序号", "设备", "品牌 / 型号", "数量", "合同单价（元）", "合同合价（元）", "供应商", "供应商报价来源", "可比中位派生（元）", "价差派生（元）"],
        rows: [
          ...mockFinancedEquipment.lines.map((line, index) => {
            const median = benchmarkMedian(line);
            return [index + 1, line.equipment, `${line.brand} / ${line.model}`, line.quantity, line.contractUnitPrice, line.quantity * line.contractUnitPrice, line.supplier, line.supplierQuoteSource, median, median === null ? null : line.quantity * (line.contractUnitPrice - median)];
          }),
          ["", "合计", "", mockFinancedEquipment.lines.reduce((sum, line) => sum + line.quantity, 0), "", mockFinancedEquipment.lines.reduce((sum, line) => sum + line.quantity * line.contractUnitPrice, 0), "", "由价格基准表中位值派生", mockFinancedEquipment.lines.every((line) => benchmarkMedian(line) !== null) ? mockFinancedEquipment.lines.reduce((sum, line) => sum + line.quantity * (benchmarkMedian(line) ?? 0), 0) : null, mockFinancedEquipment.lines.every((line) => benchmarkMedian(line) !== null) ? mockFinancedEquipment.lines.reduce((sum, line) => sum + line.quantity * (line.contractUnitPrice - (benchmarkMedian(line) ?? 0)), 0) : null],
        ],
      },
      {
        name: "价格基准",
        columns: ["设备 ID", "设备 / 型号", "单位", "低位", "中位", "高位", "本次合同单价", "来源"],
        rows: mockFinancedEquipment.lines.map((line) => [line.id, `${line.equipment} / ${line.model}`, line.priceBenchmark.unit, line.priceBenchmark.low, line.priceBenchmark.median, line.priceBenchmark.high, line.contractUnitPrice, line.priceBenchmark.sourceLabel]),
      },
      {
        name: "配置对比",
        columns: ["设备 ID", "设备 / 型号", "配置项", "单位", "本次参数", "历史中位", "同类范围", "来源"],
        rows: mockFinancedEquipment.lines.flatMap((line) => line.configuration.rows.map((row) => [line.id, `${line.equipment} / ${line.model}`, row.label, row.unit, row.current, row.median, row.range, row.sourceLabel])),
      },
      {
        name: "设备评级",
        columns: ["设备ID", "设备/型号", "供应商", "供应商评级", "品牌", "品牌评级", "评级口径", "数据状态"],
        rows: mockFinancedEquipment.lines.map((line) => [line.id, `${line.equipment} / ${line.model}`, line.supplier, line.supplierRating ?? "待核验", line.brand, line.brandRating ?? "待核验", "脱敏模拟准入评级", "脱敏模拟"]),
      },
      {
        name: "融资方案",
        columns: ["交易结构", "出租人", "期限(月)", "合同总额(元)", "首付款(元)", "融资额(元)", "融资成数(%)", "口径", "数据状态"],
        rows: [["直租", mockFinancedEquipment.lessor, mockFinancedEquipment.termMonths, 2_740_000, mockFinancedEquipment.downPaymentAmount, 1_972_800, 72, "融资额=合同总额-首付款；融资成数=融资额/合同总额", "脱敏模拟"]],
      },
      {
        name: "租金计划",
        columns: ["期次", "月租金(元)", "本金(元)", "利息(元)", "占计划总额(%)", "数据状态"],
        rows: mockTransactionRepaymentSchedule.points.map((point) => [point.period, point.rent, point.principal, point.interest, Number((point.rent / transactionRentTotal * 100).toFixed(4)), "脱敏模拟"]),
      },
    ],
  },
  {
    id: "material-production-operations",
    versionId: "material-production-operations-v1",
    kind: "excel",
    fileName: "生产运营记录.xlsx",
    label: "生产运营记录",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    availability: "available",
    isSimulated: true,
    sourceLabel: "脱敏模拟运营设备、生产阶段、电表与完工记录",
    sheets: [
      {
        name: "运营设备",
        columns: ["设备", "型号", "数量", "状态", "利用率", "额定产能", "工艺使用"],
        rows: mockOperatingEquipment.map((item) => [item.equipment, item.model, item.operatingQuantity, item.status, item.utilization, item.ratedCapacity, item.processUse]),
      },
      {
        name: "生产阶段",
        columns: ["阶段", "标题", "说明", "来源"],
        rows: mockProductionStages.map((item) => [item.stage, item.title, item.summary, item.sourceLabel]),
      },
      {
        name: "月度生产",
        columns: ["月份", "用电量（kWh）", "完工产量（件）", "口径说明"],
        rows: mockProductionEnergy.points.map((item) => [item.date, item.electricity, item.output, "月度绝对值 / 求和聚合"]),
      },
      {
        name: "人员工资",
        columns: ["月份", "工资总额（万元）", "在岗人数（人）", "人均工资（万元/人）", "口径说明", "数据状态"],
        rows: mockProductionPayrollSeries.points.map((point) => {
          const payroll = point.measures.find((measure) => measure.label === "工资总额")?.value ?? 0;
          const staff = point.measures.find((measure) => measure.label === "在岗人数")?.value ?? 0;
          return [point.label, payroll, staff, Number((payroll / staff).toFixed(2)), "工资总额 / 月末在岗人数", "脱敏模拟"];
        }),
      },
    ],
  },
];

const financedRowEvidence = mockFinancedEquipment.lines.flatMap((line, index): EvidenceReference[] => {
  const row = index + 4;
  return [
    { id: `evidence-financed-contract-${index + 1}`, label: `${line.equipment}合同设备行`, locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "合同设备", range: `B${row}:F${row}` }, locationStatus: "located", materialStatus: "confirmed" },
    { id: `evidence-financed-supplier-${index + 1}`, label: `${line.equipment}供应商报价行`, locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "合同设备", range: `G${row}:H${row}` }, locationStatus: "located", materialStatus: "confirmed" },
    { id: `evidence-financed-comparison-${index + 1}`, label: `${line.equipment}低中高与本次价格基准`, locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "价格基准", range: `B${row}:H${row}` }, locationStatus: "located", materialStatus: index === 2 ? "review" : "confirmed" },
  ];
});

const financedConfigurationEvidence = mockFinancedEquipment.lines.flatMap((line) => line.configuration.rows).map((row, index): EvidenceReference => ({
  id: row.evidenceRefs[0],
  label: `${row.label}本次、历史中位与同类范围`,
  locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "配置对比", range: `C${index + 4}:H${index + 4}` },
  locationStatus: "located",
  materialStatus: "confirmed",
}));

const financedRatingEvidence = mockFinancedEquipment.lines.flatMap((line, index): EvidenceReference[] => {
  const row = index + 4;
  return [
    { id: line.supplierRatingEvidenceRefs![0], label: `${line.supplier}供应商评级`, locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "设备评级", range: `D${row}:D${row}` }, locationStatus: "located", materialStatus: "confirmed" },
    { id: line.brandRatingEvidenceRefs![0], label: `${line.brand}品牌评级`, locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "设备评级", range: `F${row}:F${row}` }, locationStatus: "located", materialStatus: "confirmed" },
  ];
});

const transactionRepaymentEvidence = mockTransactionRepaymentSchedule.points.map((point, index): EvidenceReference => {
  const row = index + 4;
  return { id: point.evidenceRefs[0], label: `第${point.period}期租金、本金与利息`, locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "租金计划", range: `B${row}:D${row}` }, locationStatus: "located", materialStatus: "confirmed" };
});

export const mockP2Evidence: EvidenceReference[] = [
  ...financedRowEvidence,
  ...financedConfigurationEvidence,
  ...financedRatingEvidence,
  { id: "evidence-financed-total-contract", label: "融资设备合同合计", locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "合同设备", range: "D7:J7" }, locationStatus: "located", materialStatus: "confirmed" },
  { id: "evidence-transaction-project-amount", label: "项目合同总额", locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "合同设备", range: "F7:F7" }, locationStatus: "located", materialStatus: "confirmed" },
  { id: "evidence-transaction-finance-ratio-inputs", label: "融资成数派生输入", locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "融资方案", range: "D4:G4" }, locationStatus: "located", materialStatus: "confirmed" },
  { id: "evidence-transaction-plan", label: "交易融资方案", locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "融资方案", range: "A4:I4" }, locationStatus: "located", materialStatus: "confirmed" },
  ...transactionRepaymentEvidence,
  { id: "evidence-transaction-rent-first", label: "首期租金、本金与利息", locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "租金计划", range: "B4:D4" }, locationStatus: "located", materialStatus: "confirmed" },
  { id: "evidence-transaction-rent-first-12", label: "前12期租金输入", locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "租金计划", range: "B4:B15" }, locationStatus: "located", materialStatus: "confirmed" },
  { id: "evidence-transaction-rent-total", label: "36期租金输入", locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "租金计划", range: "B4:B39" }, locationStatus: "located", materialStatus: "confirmed" },
  { id: "evidence-transaction-rent-term", label: "融资期限", locator: { kind: "excel", materialId: "material-financed-equipment", materialVersionId: "material-financed-equipment-v1", sheet: "融资方案", range: "C4:C4" }, locationStatus: "located", materialStatus: "confirmed" },
  ...mockOperatingEquipment.map((item, index): EvidenceReference => ({ id: item.evidenceRefs[0], label: `${item.equipment}运营状态`, locator: { kind: "excel", materialId: "material-production-operations", materialVersionId: "material-production-operations-v1", sheet: "运营设备", range: `A${index + 4}:G${index + 4}` }, locationStatus: "located", materialStatus: index === 0 ? "confirmed" : "review" })),
  ...mockProductionStages.map((stage, index): EvidenceReference => ({ id: stage.evidenceRefs[0], label: `${stage.title}阶段记录`, locator: { kind: "excel", materialId: "material-production-operations", materialVersionId: "material-production-operations-v1", sheet: "生产阶段", range: `A${index + 4}:D${index + 4}` }, locationStatus: "located", materialStatus: "confirmed" })),
  ...mockProductionEnergy.points.flatMap((point, index): EvidenceReference[] => {
    const row = index + 4;
    return [
      { id: point.electricityEvidenceRefs[0], label: `${point.label}用电量`, locator: { kind: "excel", materialId: "material-production-operations", materialVersionId: "material-production-operations-v1", sheet: "月度生产", range: `B${row}:B${row}` }, locationStatus: "located", materialStatus: "confirmed" },
      { id: point.outputEvidenceRefs[0], label: `${point.label}完工产量`, locator: { kind: "excel", materialId: "material-production-operations", materialVersionId: "material-production-operations-v1", sheet: "月度生产", range: `C${row}:C${row}` }, locationStatus: "located", materialStatus: "confirmed" },
    ];
  }),
  ...mockProductionPayrollSeries.points.flatMap((point, index): EvidenceReference[] => {
    const row = index + 4;
    const period = point.id.replace("production-payroll-", "");
    return [
      { id: `evidence-production-payroll-${period}-amount`, label: `${point.label}工资总额`, locator: { kind: "excel", materialId: "material-production-operations", materialVersionId: "material-production-operations-v1", sheet: "人员工资", range: `B${row}:B${row}` }, locationStatus: "located", materialStatus: "confirmed" },
      { id: `evidence-production-payroll-${period}-staff`, label: `${point.label}在岗人数`, locator: { kind: "excel", materialId: "material-production-operations", materialVersionId: "material-production-operations-v1", sheet: "人员工资", range: `C${row}:C${row}` }, locationStatus: "located", materialStatus: "confirmed" },
      { id: `evidence-production-payroll-${period}-per-capita-inputs`, label: `${point.label}人均工资派生输入`, locator: { kind: "excel", materialId: "material-production-operations", materialVersionId: "material-production-operations-v1", sheet: "人员工资", range: `B${row}:C${row}` }, locationStatus: "located", materialStatus: "confirmed" },
    ];
  }),
  { id: "evidence-production-payroll-three-month-total", label: "三月工资合计输入", locator: { kind: "excel", materialId: "material-production-operations", materialVersionId: "material-production-operations-v1", sheet: "人员工资", range: "B4:B6" }, locationStatus: "located", materialStatus: "confirmed" },
  { id: "evidence-production-payroll-latest-staff", label: "最新在岗人数", locator: { kind: "excel", materialId: "material-production-operations", materialVersionId: "material-production-operations-v1", sheet: "人员工资", range: "C6:C6" }, locationStatus: "located", materialStatus: "confirmed" },
  { id: "evidence-production-payroll-latest-per-capita-inputs", label: "最新人均工资派生输入", locator: { kind: "excel", materialId: "material-production-operations", materialVersionId: "material-production-operations-v1", sheet: "人员工资", range: "B6:C6" }, locationStatus: "located", materialStatus: "confirmed" },
];

export const mockP2Facts: FactVersion[] = [
  ...mockFinancedEquipment.lines.map((line, index): FactVersion => ({
    id: line.priceBenchmark.factVersionId!,
    factKey: `transaction.price_benchmark.${line.id}`,
    dimensionId: "transaction",
    version: 1,
    label: `${line.equipment}价格区间`,
    value: `${line.priceBenchmark.low}/${line.priceBenchmark.median}/${line.priceBenchmark.high}/${line.contractUnitPrice}`,
    unit: line.priceBenchmark.unit,
    source: "mock_material_extract",
    evidenceRefs: [`evidence-financed-comparison-${index + 1}`],
    createdAt: "2026-08-08T10:16:00+09:00",
    isSimulated: true,
  })),
  ...mockFinancedEquipment.lines.flatMap((line) => line.configuration.rows.map((row): FactVersion => ({
    id: row.factVersionId!,
    factKey: `transaction.configuration.${line.id}.${row.id}`,
    dimensionId: "transaction",
    version: 1,
    label: `${line.model} ${row.label}`,
    value: `${row.current} / ${row.median} / ${row.range}`,
    unit: row.unit,
    source: "mock_material_extract",
    evidenceRefs: [...row.evidenceRefs],
    createdAt: "2026-08-08T10:17:00+09:00",
    isSimulated: true,
  }))),
];
