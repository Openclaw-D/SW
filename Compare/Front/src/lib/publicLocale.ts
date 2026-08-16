import { createContext, useContext } from "react";
import type {
  ApprovalStatus,
  DimensionId,
  EvidenceLocationStatus,
  EvidenceLocator,
  FactValue,
  HardConstraintResult,
  LocalMaterialStatus,
  ReviewActor,
  RiskLevel,
} from "../contracts/workbench";
import type { AgentRole } from "../contracts/agentCommunication";

export type PublicLocale = "en" | "zh-CN";

export const PUBLIC_LOCALE_KEY = "signal-council-public-locale-v1";
export const PublicLocaleContext = createContext<PublicLocale>("en");

export function usePublicLocale() {
  return useContext(PublicLocaleContext);
}

export function readPublicLocale(): PublicLocale {
  if (typeof window === "undefined") return "en";
  return localStorage.getItem(PUBLIC_LOCALE_KEY) === "zh-CN" ? "zh-CN" : "en";
}

export function copy(locale: PublicLocale, english: string, chinese: string) {
  return locale === "en" ? english : chinese;
}

export function containsHan(value: string) {
  return /[\u3400-\u9fff]/u.test(value);
}

export function quotedSourceText(value: string, locale: PublicLocale) {
  if (locale !== "en" || !containsHan(value) || value.startsWith("Quoted source text: ")) return value;
  return `Quoted source text: ${value}`;
}

const DIMENSION_ENGLISH: Record<DimensionId, string> = {
  compliance: "Compliance",
  transaction: "Transaction",
  production: "Operations",
  revenue: "Revenue",
  debt: "Debt",
  cashflow: "Cash flow",
};

const DIMENSION_CHINESE: Record<DimensionId, string> = {
  compliance: "合规",
  transaction: "交易",
  production: "生产",
  revenue: "营收",
  debt: "负债",
  cashflow: "流水",
};

const SYNTHETIC_INDUSTRY_SHORT_ENGLISH: Record<string, string> = {
  精工: "Precision manufacturing",
  塑成: "Plastics manufacturing",
  织造: "Textile manufacturing",
  印包: "Printing and packaging",
  电子: "Electronics manufacturing",
  玻璃: "Glass processing",
};

const CANONICAL_LABELS: Record<string, string> = {
  "主体合规": "Subject compliance",
  "交易结构": "Transaction structure",
  "生产经营": "Production and operations",
  "营收核验": "Revenue verification",
  "负债核验": "Debt verification",
  "流水核验": "Cash-flow verification",
  "风险": "Risk",
  "登记状态": "Registration status",
  "身份一致性": "Identity consistency",
  "主体身份一致性": "Subject identity consistency",
  "涉诉记录": "Litigation records",
  "涉诉记录数量": "Litigation record count",
  "禁入状态": "Prohibited-party status",
  "禁入主体状态": "Prohibited-party status",
  "主体登记": "Subject registration",
  "营业登记有效": "Business registration valid",
  "供应商评级": "Supplier grade",
  "品牌评级": "Brand grade",
  "项目金额": "Project amount",
  "融资成数": "Financing ratio",
  "融资金额": "Financed amount",
  "融资期限": "Financing term",
  "期限": "Term",
  "还款结构": "Repayment profile",
  "还款结构风险": "Repayment-profile risk",
  "首付款": "Down payment",
  "设备价格规则基准": "Rule-based equipment price benchmark",
  "设备利用率": "Equipment utilization",
  "用电产量匹配": "Electricity/output alignment",
  "用电产量匹配度": "Electricity/output alignment",
  "工艺完整度": "Process completeness",
  "工艺记录完整度": "Process-record completeness",
  "人员稳定": "Workforce stability",
  "在岗人员稳定度": "On-duty workforce stability",
  "产量连续性": "Output continuity",
  "年度营收": "Annualized revenue",
  "规则年化营收": "Rule-annualized revenue",
  "净利润": "Net profit",
  "规则净利润": "Rule-derived net profit",
  "净利率": "Net margin",
  "前12期项目租金": "Project rent for the first 12 periods",
  "租金覆盖倍数": "Rent coverage ratio",
  "派生租金覆盖倍数": "Derived rent coverage ratio",
  "订单收入覆盖": "Order-to-income coverage",
  "开票收入比": "Invoice-to-income ratio",
  "回款开票比": "Collections-to-invoices ratio",
  "征信负债": "Credit-report debt",
  "历史存量": "Historical exposure",
  "历史项目敞口": "Historical project exposure",
  "本次融资": "Current financing",
  "本次项目敞口": "Current project exposure",
  "项目总敞口": "Total project exposure",
  "重复融资核验": "Duplicate-financing check",
  "重复融资登记": "Duplicate-financing registration",
  "负债营收比": "Debt-to-revenue ratio",
  "担保义务": "Guarantee obligations",
  "担保义务占比": "Guarantee-obligation ratio",
  "短期负债占比": "Short-term debt ratio",
  "总负债": "Total debt",
  "偿债覆盖倍数": "Debt-service coverage ratio",
  "观察期流入": "Observed inflows",
  "观察期流出": "Observed outflows",
  "观察期净额": "Observed net flow",
  "观察期异常笔数": "Anomalous transactions in the observation period",
  "异常笔数": "Anomalous transaction count",
  "异常流水比例": "Anomalous cash-flow ratio",
  "流水营收匹配度": "Cash-flow/revenue alignment",
  "回款流水匹配度": "Collections/cash-flow alignment",
  "净流入比例": "Net inflow ratio",
  "经营对手方占比": "Operating-counterparty share",
  "收支真实性": "Inflow/outflow substantiation",
  "经营匹配": "Operating-activity alignment",
  "异常流水": "Anomalous cash flow",
  "企业负债": "Corporate debt",
  "个人负债": "Personal debt",
  "到期负债": "Debt due",
  "可偿还能力": "Repayment capacity",
  "合同订单": "Contracted orders",
  "发票": "Invoices",
  "回款流水": "Collections",
  "确认收入": "Recognized income",
  "流入": "Inflows",
  "流出": "Outflows",
  "净额": "Net flow",
  "用电量": "Electricity use",
  "完工产量": "Completed output",
  "工资总额": "Total payroll",
  "在岗人数": "On-duty headcount",
  "人均工资": "Payroll per person",
  "原料": "Raw material",
  "原材料": "Raw material",
  "流程": "Process",
  "产品": "Finished product",
  "状态": "Status",
  "口径": "Measurement basis",
  "设备": "Equipment",
  "合同": "Contract",
  "供应商": "Supplier",
  "可比价": "Comparable price",
  "合同金额": "Contract amount",
  "合同单价": "Contract unit price",
  "数量": "Quantity",
  "关键参数": "Key parameters",
  "当前配置": "Current configuration",
  "工艺": "Process",
  "成品": "Finished product",
  "厂区": "Site",
  "设备铭牌": "Equipment nameplate",
  "营业执照": "Business license",
  "融资租赁合同": "Finance lease agreement",
  "买卖合同": "Purchase agreement",
  "供应商报价": "Supplier quotation",
  "设备采购发票": "Equipment purchase invoices",
  "设备付款凭证": "Equipment payment records",
  "交付验收": "Delivery and acceptance record",
  "设备清单": "Equipment list",
  "厂房租赁合同": "Factory lease agreement",
  "电费及用电明细": "Electricity bills and usage detail",
  "工资发放明细": "Payroll disbursement detail",
  "销售合同": "Sales contracts",
  "销项发票": "Output VAT invoices",
  "进项发票": "Input VAT invoices",
  "纳税申报表": "Tax returns",
  "收入台账": "Revenue ledger",
  "回款台账": "Collections ledger",
  "资产负债表": "Balance sheet",
  "利润表": "Income statement",
  "企业征信报告": "Corporate credit report",
  "个人征信报告": "Personal credit report",
  "权利负担核验": "Encumbrance verification",
  "担保清单": "Guarantee register",
  "负债到期计划": "Debt maturity schedule",
  "银行流水": "Bank statements",
  "账户信息": "Account information",
  "流水主要对手方": "Primary cash-flow counterparties",
  "经营流水匹配": "Operating cash-flow matching",
  "合规": "Compliance",
  "交易": "Transaction",
  "生产": "Operations",
  "营收": "Revenue",
  "负债": "Debt",
  "流水": "Cash flow",
  "禁止": "Prohibited",
  "核实": "Verify",
  "关注": "Monitor",
  "支持": "Support",
  "项目通道敞口": "Project channel exposure",
  "企业债权人": "Enterprise creditors",
  "个人债权人": "Personal creditors",
  "负债构成": "Debt composition",
  "偿债能力": "Repayment capacity",
  "营收趋势": "Revenue trend",
  "票款互证": "Invoice-to-collection cross-check",
  "上下游构成": "Upstream/downstream composition",
  "回款账龄": "Collection aging",
  "利润与租金覆盖": "Profit and rent coverage",
  "年度净利润": "Annual net profit",
  "首期租金": "First-period rent",
  "前12期租金": "Rent for first 12 periods",
  "总租金": "Total rent",
  "期末在岗": "End-of-period staff",
  "期末人均": "End-of-period per-capita payroll",
  "三月工资": "Three-month payroll",
  "所选时段工资": "Payroll for selected periods",
  "合同设备合计": "Total contracted equipment",
  "融资额 / 合同总额": "Financed amount / contract total",
  "低位": "Low",
  "中位": "Median",
  "高位": "High",
  "本次": "Current",
  "品牌型号": "Brand / model",
  "差异": "Variance",
  "工艺使用": "Process use",
  "额定产能": "Rated capacity",
  "运营数量": "Operating quantity",
  "利用率": "Utilization",
  "厂区正面": "Site front",
  "厂区左侧": "Site left",
  "厂区右侧": "Site right",
  "厂区后侧": "Site rear",
  "厂区俯视": "Site overhead",
  "设备线正面": "Equipment line front",
  "设备线侧面": "Equipment line side",
  "设备线后侧": "Equipment line rear",
  "设备线": "Equipment line",
  "原料区": "Raw-material area",
  "成品区": "Finished-product area",
  "工艺区": "Process area",
  "车间主区": "Main workshop area",
  "法定代表人": "Legal representative",
  "实际控制人": "Controller",
  "配偶": "Spouse",
  "股东": "Shareholder",
  "亲属": "Relative",
  "股权": "Shareholding",
  "法定代表": "Legal representative",
  "实际控制": "Control",
  "关联": "Affiliate",
  "项目原件": "Project original",
  "控制关系": "Control relationship",
  "承租人": "Lessee",
  "法定代表人/实控人": "Legal representative / controller",
  "主体身份一致性交叉核验": "Cross-evidence subject identity check",
  "融资额 / 项目金额": "Financed amount / project amount",
  "项目金额 - 首付款": "Project amount - down payment",
  "完整还款计划期限": "Full repayment schedule term",
  "中风险": "Medium risk",
  "最大玻璃宽度": "Maximum glass width",
  "适用玻璃厚度": "Supported glass thickness",
  "额定加热温度": "Rated heating temperature",
  "单位面积能耗": "Energy use per unit area",
  "装机功率": "Installed power",
  "合同价": "Contract price",
  "待结构化": "Awaiting structured extraction",
  "已关联报价材料": "Quotation material linked",
  "同配置业务规则价格锚点": "Rule-based price benchmark for matching configuration",
  "报价偏离": "Quotation variance",
  "设备占位区域": "Equipment placeholder region",
  "设备与产线": "Equipment and production line",
  "工厂现场": "Factory site",
  "材料": "Materials",
  "设备总览": "Equipment overview",
  "产线总览": "Production-line overview",
  "工艺过程": "Production process",
  "厂区总览": "Site overview",
  "设备正视图": "Equipment front view",
  "设备背视图": "Equipment rear view",
  "设备侧视图": "Equipment side view",
  "厂区正面平视图": "Site front elevation",
  "厂区左侧平视图": "Site left elevation",
  "厂区右侧平视图": "Site right elevation",
  "厂区背面平视图": "Site rear elevation",
  "厂区俯视图": "Site overhead view",
  "玻璃原片入库": "Glass-sheet raw-material intake",
  "玻璃原片": "Raw glass sheets",
  "节能钢化玻璃完工": "Energy-efficient tempered-glass completion",
  "节能钢化玻璃": "Energy-efficient tempered glass",
  "上游": "Upstream",
  "下游": "Downstream",
  "核心原材料": "Core raw materials",
  "设备耗材": "Equipment consumables",
  "物流能源": "Logistics and energy",
  "制造客户": "Manufacturing customers",
  "经销渠道": "Distribution channels",
  "服务客户": "Service customers",
  "材料成本": "Material cost",
  "场地房租": "Site rent",
  "水电费用": "Utilities",
  "人工费用": "Labor cost",
  "其他费用": "Other costs",
  "本次融资金额": "Current financed amount",
  "经营银行A": "Operating bank A",
  "经营银行B": "Operating bank B",
  "融资租赁机构": "Finance lease institution",
  "其他经营负债": "Other operating debt",
  "实控人": "Controller",
  "其他股东": "Other shareholders",
  "其他关联自然人": "Other related individuals",
  "流入方": "Inflow counterparties",
  "流出方": "Outflow counterparties",
  "流水与营收匹配": "Cash-flow/revenue matching",
  "基本证照": "Basic licenses",
  "经营证明": "Operating evidence",
  "现场照片": "Site photos",
  "增信": "Credit enhancement",
  "租赁标的": "Leased asset",
  "主体核验": "Subject verification",
  "业务数据": "Business data",
  "持证授权确认": "ID-holder authorization confirmation",
  "法定代表人身份证正面": "Legal representative ID front",
  "法定代表人身份证背面": "Legal representative ID back",
  "房产明细截图": "Property-detail screenshot",
  "房产信息截图": "Property-information screenshot",
  "项目全量字段导入（完整脱敏模拟）": "Full project-field import (fully de-identified simulation)",
  "项目编号": "Project ID",
  "客户": "Customer",
  "行业": "Industry",
  "项目金额(万元)": "Project amount (CNY 10k)",
  "融资金额(万元)": "Financed amount (CNY 10k)",
  "首付款(万元)": "Down payment (CNY 10k)",
  "数据状态": "Data status",
  "业务规则生成": "Generated by business rules",
  "项目摘要": "Project summary",
  "金属精密加工": "Precision metal processing",
  "塑料制品加工": "Plastic products processing",
  "纺织制造": "Textile manufacturing",
  "印刷包装": "Printing and packaging",
  "玻璃深加工": "Deep glass processing",
  "电子制造": "Electronics manufacturing",
  "设备融资": "Equipment financing",
  "工商核验": "Business-registration verification",
  "股权资料": "Shareholding records",
  "身份证明": "Identity records",
  "系统导出": "System export",
  "回款资料": "Collection records",
  "开票资料": "Invoice records",
  "财务报表": "Financial statements",
  "电费": "Electricity records",
  "工资": "Payroll records",
  "设备照片": "Equipment photos",
  "工艺照片": "Process photos",
  "厂区照片": "Site photos",
  "流水信息": "Cash-flow records",
  "权利负担": "Encumbrance records",
  "担保资料": "Guarantee records",
  "征信明细": "Credit-report details",
  "资产证明": "Asset evidence",
  "企业征信": "Corporate credit records",
  "个人征信": "Personal credit records",
  "设备合同": "Equipment contract",
  "设备报价": "Equipment quotation",
  "设备发票": "Equipment invoices",
  "付款凭证": "Payment records",
  "前半期本金回收": "Principal recovered in the first half of the term",
  "30天内": "Within 30 days",
  "31–60天": "31–60 days",
  "60天以上": "Over 60 days",
  "观察期份额": "Observation-period share",
  "五轴加工中心": "Five-axis machining center",
  "车铣复合中心": "Turn-mill machining center",
  "立式加工中心": "Vertical machining center",
  "全电动注塑机": "All-electric injection molding machine",
  "精密注塑成型单元": "Precision injection-molding cell",
  "节能伺服注塑机": "Energy-efficient servo injection molding machine",
  "高速针织圆机": "High-speed circular knitting machine",
  "喷气织机生产线": "Air-jet loom production line",
  "电脑横机": "Computerized flat knitting machine",
  "六色胶印机": "Six-color offset press",
  "高速凹版印刷机": "High-speed gravure press",
  "窄幅柔版印刷机": "Narrow-web flexographic press",
  "高速SMT贴片线": "High-speed SMT placement line",
  "柔性电子装联线": "Flexible electronics assembly line",
  "中速SMT贴片线": "Medium-speed SMT placement line",
  "连续式钢化炉": "Continuous glass tempering furnace",
  "玻璃精密镀膜线": "Precision glass coating line",
  "节能钢化炉": "Energy-efficient glass tempering furnace",
  "单台耗气量": "Air consumption per unit",
  "机头最高速度": "Maximum carriage speed",
  "产品换线时间": "Product changeover time",
  "锁模力": "Clamping force",
  "最大镀膜宽度": "Maximum coating width",
  "印刷色组": "Printing color units",
  "标准成型周期": "Standard molding cycle",
  "针筒直径": "Cylinder diameter",
  "空循环时间": "Dry-cycle time",
  "干燥系统功率": "Drying-system power",
  "供料器槽位": "Feeder slots",
  "成圈路数": "Knitting feeds",
  "膜厚均匀性": "Film-thickness uniformity",
  "针距": "Needle gauge",
  "综框数量": "Heald-frame count",
  "理论注射容积": "Theoretical injection volume",
  "单台装机功率": "Installed power per unit",
  "整线装机功率": "Production-line installed power",
  "最大传输速度": "Maximum conveying speed",
  "最大线速度": "Maximum line speed",
  "主轴最高转速": "Maximum spindle speed",
  "最大PCB宽度": "Maximum PCB width",
  "最大纸张宽度": "Maximum sheet width",
  "动力刀塔转速": "Driven-tool turret speed",
  "针床宽度": "Needle-bed width",
  "贴装精度": "Placement accuracy",
  "理论贴装速度": "Theoretical placement speed",
  "印版厚度": "Plate thickness",
  "定位精度": "Positioning accuracy",
  "最高印刷速度": "Maximum printing speed",
  "有效印刷宽度": "Effective printing width",
  "公称筘幅": "Nominal reed width",
  "套印精度": "Registration accuracy",
  "重量重复精度": "Shot-weight repeatability",
  "机械手轴数": "Robot axes",
  "转台直径": "Rotary-table diameter",
  "最高转速": "Maximum rotation speed",
  "螺杆直径": "Screw diameter",
  "单位制品能耗": "Energy use per unit product",
  "工作台承重": "Table load capacity",
  "张力控制精度": "Tension-control accuracy",
  "刀库容量": "Tool-magazine capacity",
  "刀塔工位": "Turret stations",
  "最大车削直径": "Maximum turning diameter",
  "工作真空度": "Operating vacuum pressure",
  "最高织造速度": "Maximum weaving speed",
  "X轴行程": "X-axis travel",
  "纱嘴数量": "Yarn feeder count",
  "五轴铣削与终检": "Five-axis milling and final inspection",
  "车铣复合与测量": "Combined turning/milling and measurement",
  "铣削钻孔与抽检": "Milling, drilling, and sample inspection",
  "注塑成型与外观检验": "Injection molding and visual inspection",
  "成型与自动取件": "Molding and automated part removal",
  "伺服注塑与批次检验": "Servo injection molding and batch inspection",
  "针织与坯布检验": "Knitting and greige-fabric inspection",
  "整经织造与验布": "Warping, weaving, and fabric inspection",
  "编织与成衣片检验": "Knitting and garment-panel inspection",
  "制版印刷与色差检验": "Plate making, printing, and color-difference inspection",
  "凹版印刷与复合": "Gravure printing and lamination",
  "柔版印刷与模切": "Flexographic printing and die cutting",
  "印刷贴装回流与AOI": "Printing, placement, reflow, and AOI",
  "柔性换线与装联测试": "Flexible changeover and assembly testing",
  "贴装回流与测试": "Placement, reflow, and testing",
  "切割磨边钢化与检验": "Cutting, edge finishing, tempering, and inspection",
  "清洗镀膜与光学检验": "Cleaning, coating, and optical inspection",
  "钢化冷却与碎片检验": "Tempering, cooling, and fragmentation inspection",
};

const CANONICAL_SENTENCES: Record<string, string> = {
  "完整脱敏的确定性业务规则生成数据；仅用于单项目事实核验与交互验证，不代表真实客户、厂商核验参数、历史统计样本或统计模型": "Fully de-identified data generated by deterministic business rules. It supports single-project fact verification and interaction testing only; it is not real customer data, manufacturer-verified specifications, a historical sample, or a statistical model.",
  "必须使用同一材料版本的精确 locator；缺件只能转人工复核。": "Use an exact locator from the same material version. Missing material can only trigger manual review.",
  "关键材料缺失、冲突或无法核验，仅触发人工复核；不得据此自动拒绝。": "Missing, conflicting, or unverifiable key material triggers manual review only; it must not cause automatic rejection.",
  "已核验不利事实触发制度阻断；该结果独立于六维分数。": "A verified adverse fact triggered a policy block. This outcome is independent of the six-dimension score.",
  "已核验事实未触发制度阻断。": "Verified facts did not trigger a policy block.",
  "保持规则通过状态": "Keep the rule in pass status.",
  "按精确 locator 复核事实与规则输入": "Verify the fact and rule inputs against the exact locator.",
  "业务补充证据或作出可追溯答复。": "Business should add evidence or provide a traceable response.",
  "风控复核答复与证据后更新正式认定。": "Risk control should review the response and evidence before updating the formal determination.",
  "业务与风控按正式共同审查链处理。": "Business and risk control must handle this through the formal shared review chain.",
  "系统仅整理与提示；最终结论、审批和制度 Gate 均由既有服务端规则与授权人员确认。": "The system only organizes and flags information. Final conclusions, approvals, and policy gates remain subject to existing server rules and confirmation by authorized people.",
  "负责人须在正式审批链确认结论；Agent 建议不能写入事实、制度或审批状态。": "The accountable owner must confirm the conclusion in the formal approval chain. Agent advice cannot write facts, policy, or approval state.",
  "把分散在项目、证据、正式协同与制度 Gate 中的当前状态汇总到一个可追溯视图，减少人工整理、逐项追问和页面切换；以上数量来自当前本地模拟记录，不代表自动决策、模型准确率或已实现的时间/利润收益。": "This traceable view consolidates current project, evidence, formal-review, and policy-gate records to reduce manual collation, item-by-item follow-up, and page switching. Counts come from current local simulated records; they do not represent automated decisions, model accuracy, or realized time or profit gains.",
  "把分散在项目、证据、正式协同、制度 Gate 与单焦点会话中的当前状态汇总到一个可追溯视图，减少人工整理、逐项追问和页面切换；以上数量来自当前服务端记录，不代表自动决策、模型准确率或已实现的时间/利润收益。": "This traceable view consolidates current project, evidence, formal-review, policy-gate, and single-focus collaboration records to reduce manual collation, item-by-item follow-up, and page switching. Counts come from current server records; they do not represent automated decisions, model accuracy, or realized time or profit gains.",
  "本报告是对当前项目状态、证据、正式协同、制度 Gate 与单焦点 Agent 建议的只读汇总。Agent 内容始终为 advisory-only；报告不执行审批、不替代人工判断，也不证明真实生产模型质量或外部网络核验结果。": "This report is a read-only consolidation of current project state, evidence, formal review, policy gates, and single-focus Agent advice. Agent content is always advisory-only; the report does not approve, replace human judgment, or prove production-model quality or external-network verification.",
  "本项目全部身份、材料、金额、评分、规则结果与时间序列均由确定性业务规则生成。输出不是审批结论，不具备统计验证、违约概率预测或真实客户事实效力；最终判断必须由有权限的人工审查者结合原始材料完成。": "All identities, materials, amounts, scores, rule outcomes, and time series in this project are generated by deterministic business rules. The output is not an approval decision, statistically validated result, default-probability prediction, or real customer fact. An authorized human reviewer must make the final judgment against the original materials.",
  "项目状态与六维认定": "Project state and six-dimension determinations",
  "关键证据定位": "Key evidence locations",
  "正式共同审查未决项": "Open items in the formal shared review",
  "制度 Gate 与审批状态": "Policy gates and approval state",
  "单焦点 Agent 建议与 provenance": "Single-focus Agent advice and provenance",
  "无 locator 时显式 pending": "Explicitly pending when no locator exists",
  "不是第七维，仅为负债事实": "A debt fact, not a seventh dimension",
  "只进入人工核验，不泄漏审批结果": "Routes to human verification only; it does not imply an approval outcome",
  "由实际本金与利息计划推导为前低后高；排序规则为前高后低最安全、均衡其次、前低后高最危险。": "Derived from the actual principal-and-interest schedule as back-loaded. The rule ranks front-loaded as safest, balanced second, and back-loaded as riskiest.",
  "用电量与完工产量均由日观察值按月求和。": "Electricity use and completed output are monthly sums of daily observations.",
  "按批次和规格完成规则生成核验。": "Rule-generated checks are completed by batch and specification.",
  "按批次和规格完成模拟核验。": "Simulated checks are completed by batch and specification.",
  "仅作单台含税价格核验结构，不是厂商报价或历史统计样本。": "This is only a single-unit, tax-inclusive price-check structure; it is not a manufacturer quotation or a historical statistical sample.",
  "完整脱敏的确定性业务模拟数据；仅用于单项目事实核验与交互验证，不代表真实客户、厂商核验参数、历史统计样本或统计模型": "Fully de-identified deterministic business simulation data. It supports single-project fact verification and interaction testing only; it is not real customer data, manufacturer-verified specifications, a historical sample, or a statistical model.",
  "当前材料尚无 intelligence 结果；可由人工触发受控合成识别。": "This material has no intelligence result yet. A person may explicitly start controlled synthetic recognition.",
  "主体身份多证据已建立原子选择组": "An atomic selection group has been established for the subject-identity evidence set.",
  "请复核融资成数与实际租金计划的勾稽关系": "Review the reconciliation between the financing ratio and the actual rent schedule.",
  "工艺、用电和完工记录按日勾稽。": "Process, electricity, and completion records are reconciled daily.",
  "成品按日记录完工量。": "Completed output is recorded daily.",
  "批次记录": "Batch record",
  "完工绝对量": "Absolute completed output",
  "当前上下文存在缺失、待定位或需人工复核的信息。": "The current context contains missing, location-pending, or manual-review information.",
  "请补充或定位与本事项直接相关的原始材料，再由人工确认版本一致性。": "Add or locate the original material directly relevant to this item, then have a person confirm version consistency.",
  "现有材料不足以形成稳定风控意见，缺口只进入补件与人工复核，不自动等同拒绝。": "The current material is insufficient for a stable risk opinion. Gaps route only to supplementation and manual review; they do not mean automatic rejection.",
  "请业务侧补充对应原件、精确位置和当前版本说明。": "Business should add the corresponding original, exact location, and current-version explanation.",
  "风控侧已完成本轮证据充分性与制度当前态检查；该内容仍须人工形成正式意见。": "Risk control has completed this round's evidence-sufficiency and current-policy-state checks. A person must still form the formal opinion.",
  "领导协调权不覆盖 FactVersion、hard gate、风险否决或审批不变量。": "Leadership coordination authority does not override FactVersion, hard gates, risk vetoes, or approval invariants.",
};

const CUSTOMER_TOKENS: Record<string, string> = {
  甲辰: "Customer 01", 乙巳: "Customer 02", 丙午: "Customer 03", 丁未: "Customer 04",
  戊申: "Customer 05", 己酉: "Customer 06", 庚戌: "Customer 07", 辛亥: "Customer 08",
  壬子: "Customer 09", 癸丑: "Customer 10", 甲寅: "Customer 11", 乙卯: "Customer 12",
  丙辰: "Customer 13", 丁巳: "Customer 14", 戊午: "Customer 15", 己未: "Customer 16",
  庚申: "Customer 17", 辛酉: "Customer 18", 壬戌: "Customer 19", 癸亥: "Customer 20",
  甲子: "Customer 21", 乙丑: "Customer 22", 丙寅: "Customer 23", 丁卯: "Customer 24",
};

const UNIT_LABELS: Record<string, string> = {
  "万元": "CNY 10k",
  "万": "CNY 10k",
  "W": "CNY 10k",
  "元": "CNY",
  "元/台": "CNY/unit",
  "台": "units",
  "项": "items",
  "笔": "transactions",
  "件": "units",
  "月": "months",
  "期": "periods",
  "倍": "×",
  "万元/人": "CNY 10k/person",
  "平方米/日": "m²/day",
  "人": "people",
  "秒": "seconds",
};

const VALUE_LABELS: Record<string, string> = {
  "A级": "Grade A",
  "B级": "Grade B",
  "C级": "Grade C",
  "D级": "Grade D",
  "E级": "Grade E",
  "有效": "Valid",
  "异常": "Exception",
  "命中": "Matched",
  "未命中": "Not matched",
  "未见": "Not observed",
  "待机": "Idle",
  "运行中": "Operating",
  "维护中": "Under maintenance",
  "直租": "Direct lease",
  "均衡": "Balanced",
  "前低后高 · back_loaded": "Back-loaded · lower payments first",
  "前高后低 · front_loaded": "Front-loaded · higher payments first",
  "均衡 · balanced": "Balanced",
  back_loaded: "Back-loaded",
  front_loaded: "Front-loaded",
  balanced: "Balanced",
};

export function formatDimensionName(dimensionId: DimensionId, locale: PublicLocale, canonicalName?: string) {
  return locale === "en" ? DIMENSION_ENGLISH[dimensionId] : canonicalName ?? DIMENSION_CHINESE[dimensionId];
}

export function formatAgentRole(role: AgentRole, locale: PublicLocale) {
  const english = role === "business" ? "Business" : role === "risk" ? "Risk control" : "System";
  const chinese = role === "business" ? "业务" : role === "risk" ? "风控" : "系统";
  return copy(locale, english, chinese);
}

export function formatReviewActor(actor: ReviewActor | AgentRole | "joint" | "system", locale: PublicLocale) {
  if (actor === "joint") return copy(locale, "Business / Risk control", "业务 / 风控");
  if (actor === "system") return copy(locale, "System", "系统");
  return formatAgentRole(actor, locale);
}

export function formatApprovalStatus(status: ApprovalStatus, locale: PublicLocale) {
  const values: Record<ApprovalStatus, [string, string]> = {
    draft: ["Draft", "暂存"],
    returned: ["Returned", "已退回"],
    submitted: ["Submitted", "已提交"],
    completed: ["Completed", "已完成"],
  };
  return copy(locale, ...values[status]);
}

export function formatHardGateStatus(status: HardConstraintResult["result"], locale: PublicLocale) {
  const values: Record<HardConstraintResult["result"], [string, string]> = {
    pass: ["Pass", "通过"],
    block: ["Blocked", "阻断"],
    manual_review: ["Manual review", "人工复核"],
  };
  return copy(locale, ...values[status]);
}

export function formatRiskLevel(level: RiskLevel, locale: PublicLocale) {
  const values: Record<RiskLevel, [string, string]> = {
    support: ["Support", "支持"],
    attention: ["Attention", "关注"],
    confirm: ["Verify", "核实"],
    risk: ["Risk", "风险"],
    forbid: ["Prohibited", "禁止"],
  };
  return copy(locale, ...values[level]);
}

const PROJECT_INDUSTRY_LABELS: Record<string, string> = {
  金属精密加工: "Precision metal processing",
  塑料制品加工: "Plastic products processing",
  纺织制造: "Textile manufacturing",
  印刷包装: "Printing and packaging",
  玻璃深加工: "Deep glass processing",
  电子制造: "Electronics manufacturing",
  装备制造: "Equipment manufacturing",
  纺织服装: "Textile and apparel",
  食品加工: "Food processing",
  物流运输: "Logistics and transportation",
  医疗服务: "Medical services",
  新能源: "New energy",
};

const PROJECT_EQUIPMENT_LABELS: Record<string, string> = {
  五轴加工中心: "Five-axis machining center",
  车铣复合中心: "Turn-mill machining center",
  立式加工中心: "Vertical machining center",
  全电动注塑机: "All-electric injection molding machine",
  精密注塑成型单元: "Precision injection-molding cell",
  节能伺服注塑机: "Energy-efficient servo injection molding machine",
  高速针织圆机: "High-speed circular knitting machine",
  喷气织机生产线: "Air-jet loom production line",
  电脑横机: "Computerized flat knitting machine",
  六色胶印机: "Six-color offset press",
  高速凹版印刷机: "High-speed gravure press",
  窄幅柔版印刷机: "Narrow-web flexographic press",
  高速SMT贴片线: "High-speed SMT placement line",
  柔性电子装联线: "Flexible electronics assembly line",
  中速SMT贴片线: "Medium-speed SMT placement line",
  连续式钢化炉: "Continuous glass tempering furnace",
  玻璃精密镀膜线: "Precision glass coating line",
  节能钢化炉: "Energy-efficient glass tempering furnace",
};

const PROJECT_REGION_LABELS: Record<string, string> = {
  华东: "East China",
  华南: "South China",
  华北: "North China",
  华中: "Central China",
  西南: "Southwest China",
  东北: "Northeast China",
};

const PROJECT_STORE_LABELS: Record<string, string> = {
  规则门店一: "Rule-based team 1",
  规则门店二: "Rule-based team 2",
  规则门店三: "Rule-based team 3",
  规则门店四: "Rule-based team 4",
  上海一部: "Shanghai Team 1",
  广州中心: "Guangzhou Center",
  北京二部: "Beijing Team 2",
  武汉中心: "Wuhan Center",
  成都一部: "Chengdu Team 1",
  沈阳中心: "Shenyang Center",
};

const SYNTHETIC_SALESPERSON_LABELS: Record<string, string> = {
  业务员A: "Synthetic salesperson A",
  业务员B: "Synthetic salesperson B",
  业务员C: "Synthetic salesperson C",
  业务员D: "Synthetic salesperson D",
  业务员E: "Synthetic salesperson E",
  陈雨: "Synthetic salesperson 01",
  周宁: "Synthetic salesperson 02",
  林嘉: "Synthetic salesperson 03",
  唐安: "Synthetic salesperson 04",
  沈悦: "Synthetic salesperson 05",
  许舟: "Synthetic salesperson 06",
  顾言: "Synthetic salesperson 07",
  陆青: "Synthetic salesperson 08",
};

export function formatProjectIndustry(value: string, locale: PublicLocale) {
  return locale === "en" ? PROJECT_INDUSTRY_LABELS[value] ?? quotedSourceText(value, locale) : value;
}

export function formatProjectRegion(value: string, locale: PublicLocale) {
  return locale === "en" ? PROJECT_REGION_LABELS[value] ?? quotedSourceText(value, locale) : value;
}

export function formatProjectStore(value: string, locale: PublicLocale) {
  return locale === "en" ? PROJECT_STORE_LABELS[value] ?? quotedSourceText(value, locale) : value;
}

export function formatProjectSalesperson(value: string, locale: PublicLocale) {
  return locale === "en" ? SYNTHETIC_SALESPERSON_LABELS[value] ?? quotedSourceText(value, locale) : value;
}

export function formatProjectMaterialStatus(value: string, locale: PublicLocale) {
  const values: Record<string, [string, string]> = {
    材料齐备: ["Materials complete", "材料齐备"],
    待补材料: ["Materials outstanding", "待补材料"],
    人工复核: ["Human review", "人工复核"],
  };
  const pair = values[value];
  return pair ? copy(locale, ...pair) : locale === "en" ? quotedSourceText(value, locale) : value;
}

export function formatProjectTimeBucket(value: string, locale: PublicLocale) {
  const values: Record<string, [string, string]> = {
    "7天内": ["Within 7 days", "7天内"],
    "8–15天": ["8–15 days", "8–15天"],
    "16–30天": ["16–30 days", "16–30天"],
    "30天以上": ["Over 30 days", "30天以上"],
  };
  const pair = values[value];
  return pair ? copy(locale, ...pair) : locale === "en" ? quotedSourceText(value, locale) : value;
}

export function formatProjectFinancingType(value: string, locale: PublicLocale) {
  if (value === "设备融资") return copy(locale, "Equipment financing", value);
  return locale === "en" ? quotedSourceText(value, locale) : value;
}

export function formatSyntheticProjectCompany(value: string, projectNo: string, locale: PublicLocale) {
  if (locale !== "en") return value;
  const sequence = projectNo.match(/(\d{3})$/u)?.[1] ?? projectNo;
  return `Synthetic customer ${sequence}`;
}

export function formatEvidenceLocationStatus(status: EvidenceLocationStatus, locale: PublicLocale) {
  const values: Record<EvidenceLocationStatus, [string, string]> = {
    located: ["Located", "已定位"],
    pending: ["Location pending", "待定位"],
    unverifiable: ["Unverifiable", "无法核验"],
    version_mismatch: ["Material version mismatch", "材料版本不匹配"],
  };
  return copy(locale, ...values[status]);
}

export function formatMaterialStatus(status: LocalMaterialStatus, locale: PublicLocale) {
  const values: Record<LocalMaterialStatus, [string, string]> = {
    confirmed: ["Confirmed", "已确认"],
    review: ["Review required", "待复核"],
    conflict: ["Conflict", "冲突"],
  };
  return copy(locale, ...values[status]);
}

export function formatDataStatus(status: string, locale: PublicLocale) {
  const values: Record<string, [string, string]> = {
    simulated: ["Simulated", "模拟"],
    provider_generated_unverified: ["Provider-generated · unverified", "Provider 生成 · 未核验"],
    unavailable: ["Unavailable", "不可用"],
    loading: ["Loading", "加载中"],
    empty: ["Empty", "空"],
    error: ["Error", "错误"],
    real: ["Real provider", "真实 Provider"],
    synthetic: ["Synthetic", "合成模拟"],
    disabled: ["Disabled", "已禁用"],
    idle: ["Not run", "未运行"],
    accepted: ["Accepted", "已受理"],
    running: ["Running", "运行中"],
    succeeded: ["Completed", "已完成"],
    needs_review: ["Human review required", "待人工复核"],
    failed: ["Failed", "失败"],
    cancelled: ["Cancelled", "已取消"],
    available: ["Available", "可用"],
    pending: ["Pending", "待处理"],
    open: ["Open", "开放"],
    pending_gate: ["Pending policy gate", "待制度 Gate"],
    manual_review: ["Manual review", "人工复核"],
    block: ["Blocked", "阻断"],
    confirmed: ["Confirmed", "已确认"],
    conflict: ["Conflict", "冲突"],
  };
  const pair = values[status];
  return pair ? copy(locale, ...pair) : status;
}

export function formatCanonicalLabel(value: string, locale: PublicLocale): string {
  if (locale !== "en" || !containsHan(value)) return value;
  const exact = CANONICAL_LABELS[value] ?? VALUE_LABELS[value] ?? CANONICAL_SENTENCES[value];
  if (exact) return exact;
  const generatedCompany = /^(.+?)(甲辰|乙巳|丙午|丁未|戊申|己酉|庚戌|辛亥|壬子|癸丑|甲寅|乙卯|丙辰|丁巳|戊午|己未|庚申|辛酉|壬戌|癸亥|甲子|乙丑|丙寅|丁卯)(?:有限公司)?$/u.exec(value);
  if (generatedCompany && SYNTHETIC_INDUSTRY_SHORT_ENGLISH[generatedCompany[1]]) return `Synthetic ${CUSTOMER_TOKENS[generatedCompany[2]]} · ${SYNTHETIC_INDUSTRY_SHORT_ENGLISH[generatedCompany[1]]}`;
  const controller = /^实控人(\d+)$/u.exec(value);
  if (controller) return `Synthetic controller ${controller[1]}`;
  const supplier = /^设备供应商([甲乙丙丁])$/u.exec(value);
  if (supplier) return `Synthetic equipment supplier ${String.fromCharCode(65 + ["甲", "乙", "丙", "丁"].indexOf(supplier[1]))}`;
  const brand = /^品牌([A-Z]\d+)$/u.exec(value);
  if (brand) return `Synthetic brand ${brand[1]}`;
  const syntheticCounterparty = /^(精工|塑成|织造|印包|电子|玻璃)(\d+)$/u.exec(value);
  if (syntheticCounterparty) return `Synthetic ${SYNTHETIC_INDUSTRY_SHORT_ENGLISH[syntheticCounterparty[1]].toLowerCase()} counterparty ${syntheticCounterparty[2]}`;
  const percentage = /^(.+?)(-?\d+(?:\.\d+)?)%$/u.exec(value);
  if (percentage) {
    const label = CANONICAL_LABELS[percentage[1].trim()] ?? VALUE_LABELS[percentage[1].trim()];
    if (label) return `${label} ${percentage[2]}%`;
  }
  const period = /^(\d+)\s*期$/u.exec(value);
  if (period) return `${period[1]} periods`;
  const debtScenario = /^(\d+)(直|核心)([\d.]+)W$/u.exec(value);
  if (debtScenario) return `${debtScenario[1]} periods · ${debtScenario[2] === "直" ? "direct lease" : "core case"} · ${debtScenario[3]} CNY 10k`;
  const exposureLimit = /^历史存量 \+ 本次融资；全局上限([\d,.]+)W$/u.exec(value);
  if (exposureLimit) return `Historical exposure + current financing; global limit ${exposureLimit[1]} CNY 10k`;
  const materialDescriptor = /^(.+?)\s+\/\s+(.+?)\s+·\s+(\.[A-Z0-9]+)$/u.exec(value);
  if (materialDescriptor) return `${formatCanonicalLabel(materialDescriptor[1], locale)} / ${quotedSourceText(materialDescriptor[2], locale)} · ${materialDescriptor[3]}`;
  const materialPath = /^(.+?)\s+\/\s+(.+)$/u.exec(value);
  if (materialPath) return `${formatCanonicalLabel(materialPath[1], locale)} / ${quotedSourceText(materialPath[2], locale)}`;
  const parts = value.split(" · ");
  if (parts.length > 1) return parts.map((part) => formatCanonicalLabel(part, locale)).join(" · ");
  const dated = /^(\d{4}-\d{2}-\d{2})\s+(.+)$/u.exec(value);
  if (dated) return `${dated[1]} · ${formatCanonicalLabel(dated[2], locale)}`;
  const month = /^(\d{4})年(\d{1,2})月$/u.exec(value);
  if (month) return `${month[1]}-${month[2].padStart(2, "0")}`;
  const grade = /^([A-E])级$/u.exec(value);
  if (grade) return `Grade ${grade[1]}`;
  return quotedSourceText(value, locale);
}

export function formatUnit(value: string | null | undefined, locale: PublicLocale) {
  if (!value || locale !== "en") return value ?? "";
  return UNIT_LABELS[value] ?? (containsHan(value) ? quotedSourceText(value, locale) : value);
}

export function formatFactValue(value: FactValue, unit: string | null, locale: PublicLocale) {
  if (typeof value === "boolean") return copy(locale, value ? "Yes" : "No", value ? "是" : "否");
  if (value === null) return copy(locale, "Not provided", "未提供");
  const raw = String(value);
  const display = locale === "en" ? VALUE_LABELS[raw] ?? (containsHan(raw) ? quotedSourceText(raw, locale) : raw) : raw;
  const displayUnit = formatUnit(unit, locale);
  return displayUnit ? `${display} ${displayUnit}` : display;
}

export function formatEvidenceLocator(locator: EvidenceLocator | null, status: EvidenceLocationStatus, locale: PublicLocale) {
  if (!locator) return formatEvidenceLocationStatus(status, locale);
  if (locator.kind === "excel") return `${locator.sheet}!${locator.range}`;
  if (locator.kind === "pdf") return copy(locale, `Page ${locator.page}`, `第 ${locator.page} 页`);
  if (locator.kind === "image") return copy(locale, "Image region", "图像区域");
  if (locator.kind === "media") return copy(locale, `${locator.startSeconds}–${locator.endSeconds} seconds`, `${locator.startSeconds}–${locator.endSeconds} 秒`);
  return copy(locale, `${locator.pointIds.length} scene points`, `场景点 ${locator.pointIds.length} 个`);
}

export function formatEvidenceLocatorSummary(value: string, status: EvidenceLocationStatus, locale: PublicLocale) {
  if (locale !== "en") return value;
  const exact: Record<string, string> = {
    待定位: "Location pending",
    无法核验: "Unverifiable",
    材料版本不匹配: "Material version mismatch",
    未定位: "Not located",
    图像区域: "Image region",
  };
  if (exact[value]) return exact[value];
  const pdf = /^第\s*(\d+)\s*页$/u.exec(value);
  if (pdf) return `Page ${pdf[1]}`;
  const media = /^(\d+(?:\.\d+)?)–(\d+(?:\.\d+)?)\s*秒$/u.exec(value);
  if (media) return `${media[1]}–${media[2]} seconds`;
  const scene = /^场景点\s*(\d+)\s*个$/u.exec(value);
  if (scene) return `${scene[1]} scene points`;
  return containsHan(value) ? quotedSourceText(value, locale) : value || formatEvidenceLocationStatus(status, locale);
}

function formatGeneratedProjectName(value: string) {
  const match = /^系统生成·(.+?)(甲辰|乙巳|丙午|丁未|戊申|己酉|庚戌|辛亥|壬子|癸丑|甲寅|乙卯|丙辰|丁巳|戊午|己未|庚申|辛酉|壬戌|癸亥|甲子|乙丑|丙寅|丁卯)(?:有限公司)?(?:·(.+))?$/u.exec(value);
  if (!match) return null;
  const financing = /^(.+)设备融资$/u.exec(match[3] ?? "");
  const suffix = financing
    ? ` · ${PROJECT_EQUIPMENT_LABELS[financing[1]] ?? quotedSourceText(financing[1], "en")} financing`
    : match[3] ? ` · ${quotedSourceText(match[3], "en")}` : "";
  return `Synthetic ${CUSTOMER_TOKENS[match[2]]} · ${SYNTHETIC_INDUSTRY_SHORT_ENGLISH[match[1]] ?? quotedSourceText(match[1], "en")}${suffix}`;
}

export function formatCanonicalNarrative(value: string, locale: PublicLocale): string {
  if (locale !== "en" || !containsHan(value)) return value;
  const exact = CANONICAL_SENTENCES[value] ?? CANONICAL_LABELS[value] ?? VALUE_LABELS[value];
  if (exact) return exact;
  const generatedName = formatGeneratedProjectName(value);
  if (generatedName) return generatedName;
  const dimensionSummary = /^(合规|交易|生产|营收|负债|流水)由已核验业务事实按版本化规则计算；材料状态只影响置信度。$/u.exec(value);
  if (dimensionSummary) {
    const dimensionIdsByName = { 合规: "compliance", 交易: "transaction", 生产: "production", 营收: "revenue", 负债: "debt", 流水: "cashflow" } as const;
    const id = dimensionIdsByName[dimensionSummary[1] as keyof typeof dimensionIdsByName];
    return `${DIMENSION_ENGLISH[id]} is calculated from verified business facts under versioned rules; material status affects confidence only.`;
  }
  const overall = /^六维等权规则分\s*([\d.]+)；风险为全局五级汇总，制度 Gate 独立判断。$/u.exec(value);
  if (overall) return `Equal-weight six-dimension rule score: ${overall[1]}. The global five-level risk summary is separate from the policy gate.`;
  const dimensionRisk = /^该维度规则分\s*([\d.]+)，需回到原始材料核验。$/u.exec(value);
  if (dimensionRisk) return `Rule score for this dimension: ${dimensionRisk[1]}. Verify it against the original material.`;
  const gateCheck = /^制度 Gate：(pass|block|manual_review)；阻断规则\s*(\d+)\s*条。$/u.exec(value);
  if (gateCheck) return `Policy gate: ${formatHardGateStatus(gateCheck[1] as HardConstraintResult["result"], "en")}; ${gateCheck[2]} blocking rules.`;
  const openCheck = /^正式未决项：(\d+)\s*条；未完成定位证据：(\d+)\s*条。$/u.exec(value);
  if (openCheck) return `Formal open items: ${openCheck[1]}; evidence items without completed locations: ${openCheck[2]}.`;
  const prohibitedStatus = /^禁入主体状态：(pass|block|manual_review)$/u.exec(value);
  if (prohibitedStatus) return `Prohibited-party status: ${formatHardGateStatus(prohibitedStatus[1] as HardConstraintResult["result"], "en")}`;
  const dateRange = /^(\d{4}-\d{2}-\d{2})\s+至\s+(\d{4}-\d{2}-\d{2})(?:\s+·\s+(.+))?$/u.exec(value);
  if (dateRange) return `${dateRange[1]} to ${dateRange[2]}${dateRange[3] ? ` · ${formatCanonicalNarrative(dateRange[3], locale)}` : ""}`;
  const specificationLine = value.split(" · ");
  if (specificationLine.length > 1 && specificationLine.every((item) => /^.+?\s+-?[\d,.]+\s*[^\s]+$/u.test(item))) {
    return specificationLine.map((item) => {
      const match = /^(.+?)\s+(-?[\d,.]+)\s*(.+)$/u.exec(item)!;
      return `${formatCanonicalLabel(match[1], locale)} ${match[2]} ${formatUnit(match[3], locale)}`;
    }).join(" · ");
  }
  const equipmentContract = /^(SYN-[\w-]+)\s+设备合同$/u.exec(value);
  if (equipmentContract) return `${equipmentContract[1]} equipment contract`;
  const materialDescriptor = /^(.+?)\s+\/\s+(.+?)\s+·\s+(\.[A-Z0-9]+)$/u.exec(value);
  if (materialDescriptor) return `${formatCanonicalLabel(materialDescriptor[1], locale)} / ${quotedSourceText(materialDescriptor[2], locale)} · ${materialDescriptor[3]}`;
  const exposureLimit = /^历史存量 \+ 本次融资；全局上限([\d,.]+)W$/u.exec(value);
  if (exposureLimit) return `Historical exposure + current financing; global limit ${exposureLimit[1]} CNY 10k`;
  const debtScenario = /^(\d+)(直|核心)([\d.]+)W$/u.exec(value);
  if (debtScenario) return `${debtScenario[1]} periods · ${debtScenario[2] === "直" ? "direct lease" : "core case"} · ${debtScenario[3]} CNY 10k`;
  const labelledAmount = /^(.+?)([\d,.]+)\s+CNY 10k\s+·\s+([\d.]+)%$/u.exec(value);
  if (labelledAmount) return `${formatCanonicalLabel(labelledAmount[1], locale)} ${labelledAmount[2]} CNY 10k · ${labelledAmount[3]}%`;
  const percentageLabel = /^(.+?)(-?\d+(?:\.\d+)?)%$/u.exec(value);
  if (percentageLabel) {
    const label = formatCanonicalLabel(percentageLabel[1].trim(), locale);
    if (!label.startsWith("Quoted source text: ")) return `${label} ${percentageLabel[2]}%`;
  }
  const month = /^(\d{4})年(\d{1,2})月$/u.exec(value);
  if (month) return `${month[1]}-${month[2].padStart(2, "0")}`;
  const numericUnit = /^([+-]?[\d,.]+)\s*(万元|万|W|元|台|项|笔|件|月|期|倍|平方米\/日)$/u.exec(value);
  if (numericUnit) return `${numericUnit[1]} ${formatUnit(numericUnit[2], "en")}`;
  const axisCount = /^(\d+)\s*轴$/u.exec(value);
  if (axisCount) return `${axisCount[1]} axes`;
  const spindleCount = /^(\d+)\s*主轴$/u.exec(value);
  if (spindleCount) return `${spindleCount[1]} spindles`;
  const label = formatCanonicalLabel(value, locale);
  if (!label.startsWith("Quoted source text: ")) return label;
  const translatedValue = VALUE_LABELS[value];
  if (translatedValue) return translatedValue;
  return quotedSourceText(value, locale);
}

/** Domain-routed API display formatter. It never mutates the canonical payload. */
export function formatCanonicalText(value: string, locale: PublicLocale) {
  return formatCanonicalNarrative(value, locale);
}

export function formatServiceMessage(value: string | null | undefined, locale: PublicLocale) {
  if (!value) return copy(locale, "No service detail was returned.", "服务未返回详情。");
  return formatCanonicalNarrative(value, locale);
}

export function formatReviewEventType(value: string, locale: PublicLocale) {
  const values: Record<string, [string, string]> = {
    fact_version_created: ["Fact version created", "事实版本创建"],
    business_correction_submitted: ["Business correction submitted", "业务修正已提交"],
    risk_question_submitted: ["Risk question submitted", "风控问题已提交"],
    risk_answer_submitted: ["Risk response submitted", "风控答复已提交"],
    business_answer_submitted: ["Business response submitted", "业务答复已提交"],
    issue_opened: ["Issue opened", "问题已建立"],
    policy_result_recorded: ["Policy result recorded", "制度结果已记录"],
  };
  const pair = values[value];
  return pair ? copy(locale, ...pair) : value;
}

export function formatCollaborationKind(value: string, locale: PublicLocale) {
  const values: Record<string, [string, string]> = {
    pending_question: ["Awaiting response", "待回复"],
    focus_event: ["Focus event", "焦点事件"],
    confirmed_conclusion: ["Explicit conclusion", "明确结论"],
    material_reference: ["Material reference", "材料引用"],
  };
  const pair = values[value];
  return pair ? copy(locale, ...pair) : value;
}

export const IMAGE_TO_3D_BOUNDARY = {
  en: "Image-to-3D reconstruction unavailable — no reconstruction provider, job, or independently verified asset provenance is connected.",
  "zh-CN": "图像转 3D 重建不可用——尚未接入重建 provider、任务或经独立验证的资产 provenance。",
} as const;

/**
 * Compatibility is deliberately opt-in and decorative-only. Critical business
 * surfaces use component copy and the domain formatters above.
 */
export function translateEnglishSurface(root: HTMLElement) {
  for (const element of root.querySelectorAll<HTMLElement>("[data-legacy-decorative-copy]")) {
    for (const node of element.childNodes) {
      if (node.nodeType !== Node.TEXT_NODE || !node.textContent) continue;
      const translated = CANONICAL_LABELS[node.textContent.trim()];
      if (translated) node.textContent = node.textContent.replace(node.textContent.trim(), translated);
    }
  }
}

/** Kept for the public-entry regression surface; critical UI does not call it. */
export function translatePublicText(value: string, locale: PublicLocale) {
  if (locale === "en" && (value === "signal-council" || value === "中")) return value;
  return formatCanonicalNarrative(value, locale);
}
