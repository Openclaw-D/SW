import type { AgentMessage, AgentResponseDepth, AgentResponseFocus, ChatAgentRole } from "../contracts/agentCommunication";
import type { CSSProperties } from "react";
import { useState } from "react";
import { copy, usePublicLocale } from "../lib/publicLocale";
import { Icon } from "./icons";

export interface CollaborationViewSettings {
  enabledAgents: Record<ChatAgentRole, boolean>;
  sendOnEnter: boolean;
  autoScroll: boolean;
  compactMessages: boolean;
  showProvenance: boolean;
  responseDepth: AgentResponseDepth;
  responseFocus: AgentResponseFocus;
  customGuidance: string;
}

export const DEFAULT_COLLABORATION_VIEW_SETTINGS: CollaborationViewSettings = {
  enabledAgents: { business: true, risk: true },
  sendOnEnter: true,
  autoScroll: true,
  compactMessages: false,
  showProvenance: false,
  responseDepth: "brief",
  responseFocus: "balanced",
  customGuidance: "",
};

type SettingsSectionId = "overview" | "routing" | "response" | "interface" | "safety";

function SettingSwitch({ checked, description, label, onChange }: {
  checked: boolean;
  description: string;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="agent-setting-switch">
      <span><strong>{label}</strong><small>{description}</small></span>
      <input checked={checked} onChange={(event) => onChange(event.target.checked)} type="checkbox" />
      <i aria-hidden="true" />
    </label>
  );
}

export function AgentSettingsDashboard({ messages, onChange, onClose, settings }: {
  messages: AgentMessage[];
  onChange: (settings: CollaborationViewSettings) => void;
  onClose: () => void;
  settings: CollaborationViewSettings;
}) {
  const locale = usePublicLocale();
  const [activeSection, setActiveSection] = useState<SettingsSectionId>("overview");
  const agentMessages = messages.filter((message) => message.authorType === "agent");
  const humanMessages = messages.filter((message) => message.authorType === "human");
  const businessReplies = agentMessages.filter((message) => message.role === "business").length;
  const riskReplies = agentMessages.filter((message) => message.role === "risk").length;
  const citationCount = messages.reduce((total, message) => total + message.citations.length, 0);
  const update = <Key extends keyof CollaborationViewSettings>(key: Key, value: CollaborationViewSettings[Key]) => onChange({ ...settings, [key]: value });
  const toggleAgent = (role: ChatAgentRole, enabled: boolean) => update("enabledAgents", { ...settings.enabledAgents, [role]: enabled });
  const maximumReplies = Math.max(1, businessReplies, riskReplies);
  const responseFocus = settings.responseFocus ?? "balanced";
  const customGuidance = settings.customGuidance ?? "";

  const messageTotal = humanMessages.length + agentMessages.length;
  const humanPercent = Math.round((humanMessages.length / Math.max(1, messageTotal)) * 100);
  const agentPercent = Math.round((agentMessages.length / Math.max(1, messageTotal)) * 100);
  const donutCircumference = 2 * Math.PI * 42;
  const humanArc = donutCircumference * (messageTotal === 0 ? 0 : humanMessages.length / messageTotal);
  const agentArc = donutCircumference * (messageTotal === 0 ? 0 : agentMessages.length / messageTotal);

  const cumulativeAgentMessages: Array<{ sequence: number; cumulative: number }> = [{ sequence: 0, cumulative: 0 }];
  for (let index = 0; index < messages.length; index += 1) {
    cumulativeAgentMessages.push({
      sequence: index + 1,
      cumulative: cumulativeAgentMessages[index].cumulative + (messages[index].authorType === "agent" ? 1 : 0),
    });
  }
  const latestCumulative = cumulativeAgentMessages[cumulativeAgentMessages.length - 1].cumulative;
  const maximumSequence = Math.max(1, messages.length);
  const maximumCumulative = Math.max(1, latestCumulative);
  const sparkPoints = cumulativeAgentMessages.map((point) => ({
    x: 12 + (point.sequence / maximumSequence) * 316,
    y: 112 - (point.cumulative / maximumCumulative) * 96,
  }));
  const sparkPath = sparkPoints.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const sparkArea = `12,112 ${sparkPath} 328,112`;
  const sparkEnd = sparkPoints[sparkPoints.length - 1];

  const sections: Array<{ id: SettingsSectionId; label: string; hint: string }> = [
    { id: "overview", label: copy(locale, "Overview", "总览"), hint: copy(locale, "Metrics and charts", "指标与图表") },
    { id: "routing", label: copy(locale, "Agent routing", "Agent 路由"), hint: copy(locale, "Business and Risk only", "仅业务与风控") },
    { id: "response", label: copy(locale, "Response preferences", "回复偏好"), hint: copy(locale, "Advisory only", "仅建议性") },
    { id: "interface", label: copy(locale, "Interface behavior", "界面行为"), hint: copy(locale, "Chat interactions", "群聊交互") },
    { id: "safety", label: copy(locale, "Safety boundaries", "安全边界"), hint: copy(locale, "Server guardrails", "服务端强约束") },
  ];

  return (
    <section aria-label={copy(locale, "Agent settings dashboard", "Agent 设置 Dashboard")} className="agent-settings-dashboard">
      <header>
        <div><span className="agent-settings-kicker"><Icon name="settings" />{copy(locale, "Settings", "设置")}</span><h3>{copy(locale, "Two-Agent collaboration dashboard", "双 Agent 协作 Dashboard")}</h3><p>{copy(locale, "Business and Risk are the only routable Agents. Settings manages the current chat experience and never speaks in the conversation.", "群聊只路由业务与风控两个 Agent；设置只管理当前群聊体验，不参与发言。")}</p></div>
        <button aria-label={copy(locale, "Close settings dashboard", "关闭设置 Dashboard")} onClick={onClose} type="button">×</button>
      </header>

      <div className="agent-settings-console">
        <nav aria-label={copy(locale, "Settings sections", "设置分区")} className="agent-settings-nav">
          <span className="agent-settings-nav-caption">{copy(locale, "Console", "控制台")}</span>
          {sections.map((section) => (
            <button
              key={section.id}
              type="button"
              className={activeSection === section.id ? "is-active" : undefined}
              aria-current={activeSection === section.id ? "true" : undefined}
              onClick={() => setActiveSection(section.id)}
            >
              <strong>{section.label}</strong>
              <small>{section.hint}</small>
            </button>
          ))}
        </nav>

        <div aria-live="polite" className="agent-settings-detail">
          {activeSection === "overview" ? (
            <section aria-label={copy(locale, "Overview", "总览")}>
              <div className="agent-settings-section-title">
                <div><strong>{copy(locale, "Overview", "总览")}</strong><small>{copy(locale, "Conversation metrics drawn with native React, CSS, and SVG only.", "会话指标由原生 React/CSS/SVG 绘制，不引入图表依赖。")}</small></div>
              </div>

              <div className="agent-settings-metrics" aria-label={copy(locale, "Conversation metrics", "会话指标")}>
                <article><span>{copy(locale, "Visible messages", "可见消息")}</span><strong>{messages.length}</strong><small>{humanMessages.length} {copy(locale, "human", "人工")} · {agentMessages.length} Agent</small></article>
                <article><span>{copy(locale, "Business replies", "业务回复")}</span><strong>{businessReplies}</strong><i style={{ "--metric-ratio": `${businessReplies / maximumReplies}` } as CSSProperties} /></article>
                <article><span>{copy(locale, "Risk replies", "风控回复")}</span><strong>{riskReplies}</strong><i style={{ "--metric-ratio": `${riskReplies / maximumReplies}` } as CSSProperties} /></article>
                <article><span>{copy(locale, "Evidence citations", "证据引用")}</span><strong>{citationCount}</strong><small>{copy(locale, "Traceable references", "可追踪引用")}</small></article>
              </div>

              <div className="agent-settings-charts">
                <figure className="agent-chart">
                  <div className="agent-chart-title"><strong>{copy(locale, "Human vs Agent messages", "人工与 Agent 消息")}</strong><small>{copy(locale, "Donut", "环形图")}</small></div>
                  <div className="agent-donut-layout">
                    <svg className="agent-chart-donut" viewBox="0 0 120 120" role="img" aria-label={`消息构成环形图：人工消息 ${humanMessages.length} 条，Agent 消息 ${agentMessages.length} 条，合计 ${messageTotal} 条`}>
                      <g fill="none" strokeWidth={13} transform="rotate(-90 60 60)">
                        <circle className="agent-donut-track" cx="60" cy="60" r="42" />
                        <circle className="agent-donut-human" cx="60" cy="60" r="42" strokeDasharray={`${humanArc} ${donutCircumference - humanArc}`} />
                        <circle className="agent-donut-agent" cx="60" cy="60" r="42" strokeDasharray={`${agentArc} ${donutCircumference - agentArc}`} strokeDashoffset={-humanArc} />
                      </g>
                      <text x="60" y="58" textAnchor="middle" fontSize="21" fontWeight="700" fill="#242321">{messageTotal}</text>
                      <text x="60" y="73" textAnchor="middle" fontSize="10" fill="#6d675e">{copy(locale, "messages", "消息")}</text>
                    </svg>
                    <div className="agent-chart-legend">
                      <div><i aria-hidden="true" className="is-human" /><span>{copy(locale, "Human", "人工")}</span><b>{humanMessages.length} · {humanPercent}%</b></div>
                      <div><i aria-hidden="true" className="is-agent" /><span>Agent</span><b>{agentMessages.length} · {agentPercent}%</b></div>
                    </div>
                  </div>
                </figure>

                <figure className="agent-chart">
                  <div className="agent-chart-title"><strong>{copy(locale, "Business vs Risk replies", "业务与风控 Agent 回复")}</strong><small>{copy(locale, "Bars", "条形图")}</small></div>
                  <div className="agent-chart-bars" role="img" aria-label={`Agent 回复条形图：业务 Agent 回复 ${businessReplies} 条，风控 Agent 回复 ${riskReplies} 条`}>
                    <div className="agent-bar-row">
                      <span>{copy(locale, "Business", "业务")}</span>
                      <i aria-hidden="true"><b style={{ "--bar-ink": "#242321", "--bar-ratio": `${businessReplies / maximumReplies}` } as CSSProperties} /></i>
                      <b>{businessReplies}</b>
                    </div>
                    <div className="agent-bar-row">
                      <span>{copy(locale, "Risk", "风控")}</span>
                      <i aria-hidden="true"><b style={{ "--bar-ink": "#8a8378", "--bar-ratio": `${riskReplies / maximumReplies}` } as CSSProperties} /></i>
                      <b>{riskReplies}</b>
                    </div>
                  </div>
                </figure>

                <figure className="agent-chart">
                  <div className="agent-chart-title"><strong>{copy(locale, "Cumulative Agent messages", "Agent 消息累计")}</strong><small>{copy(locale, "Line", "折线图")}</small></div>
                  <svg className="agent-chart-line" viewBox="0 0 340 132" role="img" aria-label={`Agent 消息累计折线图：按消息序号 0 至 ${messages.length}，累计 Agent 消息 ${latestCumulative} 条`}>
                    <line className="agent-line-grid" x1="12" y1="16" x2="328" y2="16" />
                    <line className="agent-line-grid" x1="12" y1="64" x2="328" y2="64" />
                    <line className="agent-line-grid" x1="12" y1="112" x2="328" y2="112" />
                    <text x="328" y="13" textAnchor="end">{maximumCumulative}</text>
                    <text x="328" y="61" textAnchor="end">{Math.round(maximumCumulative / 2)}</text>
                    <polygon className="agent-line-area" points={sparkArea} />
                    <polyline className="agent-line-path" points={sparkPath} />
                    <circle className="agent-line-point" cx={sparkEnd.x} cy={sparkEnd.y} r="3.2" />
                    <text x="12" y="128">0</text>
                    <text x="328" y="128" textAnchor="end">{messages.length}</text>
                  </svg>
                  <div className="agent-chart-readout">
                    <span>{copy(locale, "Message sequence", "消息序号")}</span><b>0–{messages.length}</b>
                    <span>{copy(locale, "Cumulative Agent messages", "累计 Agent 消息")}</span><b>{latestCumulative}</b>
                  </div>
                </figure>
              </div>
            </section>
          ) : null}

          {activeSection === "routing" ? (
            <section aria-label={copy(locale, "Agent routing", "Agent 路由")}>
              <div className="agent-settings-section-title">
                <div><strong>{copy(locale, "Agent routing", "Agent 路由")}</strong><small>{copy(locale, "Control which business Agents can be selected in this chat.", "控制在当前群聊中可以选择的业务 Agent。")}</small></div>
              </div>
              <p className="agent-settings-note">{copy(locale, "Routable Agents remain Business and Risk only. system/settings is a non-Agent control plane and never posts messages.", "可路由 Agent 仅保留业务与风控；system/settings 是非 Agent 控制面，不参与群聊发言。")}</p>
              <ul className="agent-settings-route-list">
                <li>
                  <div className="agent-route-title"><span><Icon name="business" /></span><div><strong>{copy(locale, "Business Agent", "业务 Agent")}</strong><small>{copy(locale, "Project facts and material gaps", "项目事实与材料缺口")}</small></div><b>{settings.enabledAgents.business ? copy(locale, "Enabled", "已启用") : copy(locale, "Paused", "已暂停")}</b></div>
                  <SettingSwitch checked={settings.enabledAgents.business} description={copy(locale, "Controls whether @Business can be selected in this page.", "控制当前页面是否可以选择 @业务。")} label={copy(locale, "Allow routing", "允许路由")} onChange={(checked) => toggleAgent("business", checked)} />
                </li>
                <li>
                  <div className="agent-route-title"><span><Icon name="risk" /></span><div><strong>{copy(locale, "Risk Agent", "风控 Agent")}</strong><small>{copy(locale, "Evidence sufficiency and policy checks", "证据充分性与制度核验")}</small></div><b>{settings.enabledAgents.risk ? copy(locale, "Enabled", "已启用") : copy(locale, "Paused", "已暂停")}</b></div>
                  <SettingSwitch checked={settings.enabledAgents.risk} description={copy(locale, "Controls whether @Risk can be selected in this page.", "控制当前页面是否可以选择 @风控。")} label={copy(locale, "Allow routing", "允许路由")} onChange={(checked) => toggleAgent("risk", checked)} />
                </li>
              </ul>
            </section>
          ) : null}

          {activeSection === "response" ? (
            <section aria-label={copy(locale, "Response preferences", "回复偏好")}>
              <div className="agent-settings-section-title">
                <div><strong>{copy(locale, "Response preferences", "回复偏好")}</strong><small>{copy(locale, "Short, scannable replies for this chat.", "短、准、可扫读的群聊回复。")}</small></div>
              </div>
              <p className="agent-settings-note">{copy(locale, "Every Agent reply uses the same three-step structure. Focus can change, but length and authority boundaries cannot.", "每条 Agent 回复固定三步；可以调整侧重，但不能突破短答与权限边界。")}</p>
              <div className="agent-settings-fields">
                <div aria-label={copy(locale, "Fixed three-step reply, up to 220 characters", "固定三步短答 · 最多 220 字")} className="agent-settings-fixed-format">
                  <strong>{copy(locale, "Fixed format", "固定短答")}</strong>
                  <span><b>1</b>{copy(locale, "Locate the category", "定位类别")}</span>
                  <span><b>2</b>{copy(locale, "Core data and judgement", "核心数据与判断")}</span>
                  <span><b>3</b>{copy(locale, "One next action", "一个下一步动作")}</span>
                </div>
                <div className="agent-settings-field">
                  <label htmlFor="agent-response-focus"><strong>{copy(locale, "Response focus", "回复侧重")}</strong><small>{copy(locale, "Advisory emphasis for replies.", "回复侧重建议。")}</small></label>
                  <select id="agent-response-focus" value={responseFocus} onChange={(event) => {
                    const value = event.target.value;
                    if (value === "balanced" || value === "risk" || value === "evidence" || value === "next_steps") update("responseFocus", value);
                  }}>
                    <option value="balanced">{copy(locale, "Balanced", "均衡")}</option>
                    <option value="risk">{copy(locale, "Risk", "风险")}</option>
                    <option value="evidence">{copy(locale, "Evidence", "证据")}</option>
                    <option value="next_steps">{copy(locale, "Next steps", "下一步")}</option>
                  </select>
                </div>
              </div>
              <div className="agent-settings-field">
                <label htmlFor="agent-custom-guidance"><strong>{copy(locale, "Custom guidance", "自定义引导")}</strong><small>{copy(locale, "Optional advisory note for Agent replies in this chat.", "可选的本次群聊 Agent 回复引导建议。")}</small></label>
                <textarea
                  id="agent-custom-guidance"
                  maxLength={500}
                  value={customGuidance}
                  placeholder={copy(locale, "e.g. Prioritize contract amount evidence.", "例如：优先看合同金额证据。")}
                  onChange={(event) => update("customGuidance", event.target.value)}
                />
                <div className="agent-settings-count">
                  <span>{copy(locale, "Advisory only; formal constraints stay unchanged.", "仅建议性，正式约束保持不变。")}</span>
                  <b>{customGuidance.length}/500</b>
                </div>
              </div>
            </section>
          ) : null}

          {activeSection === "interface" ? (
            <section aria-label={copy(locale, "Interface behavior", "界面行为")}>
              <div className="agent-settings-section-title">
                <div><strong>{copy(locale, "Conversation behavior", "群聊行为")}</strong><small>{copy(locale, "Changes apply immediately to the current page.", "修改后立即作用于当前页面。")}</small></div>
              </div>
              <div className="agent-settings-switch-grid">
                <SettingSwitch checked={settings.sendOnEnter} description={copy(locale, "Shift+Enter always starts a new line.", "Shift+Enter 始终换行。")} label={copy(locale, "Enter to send", "回车发送")} onChange={(checked) => update("sendOnEnter", checked)} />
                <SettingSwitch checked={settings.autoScroll} description={copy(locale, "Follow new messages and Agent status.", "跟随新消息与 Agent 状态。")} label={copy(locale, "Auto-scroll", "自动滚动")} onChange={(checked) => update("autoScroll", checked)} />
                <SettingSwitch checked={settings.compactMessages} description={copy(locale, "Reduce message spacing for dense review.", "压缩消息间距，便于密集审查。")} label={copy(locale, "Compact messages", "紧凑消息")} onChange={(checked) => update("compactMessages", checked)} />
                <SettingSwitch checked={settings.showProvenance} description={copy(locale, "Optionally show provider and model for technical audit.", "仅在技术审计时显示 provider 与 model。")} label={copy(locale, "Show technical provenance", "显示技术来源")} onChange={(checked) => update("showProvenance", checked)} />
              </div>
            </section>
          ) : null}

          {activeSection === "safety" ? (
            <section aria-label={copy(locale, "Safety boundaries", "安全边界")}>
              <div className="agent-settings-section-title">
                <div><strong>{copy(locale, "Safety boundaries", "安全边界")}</strong><small>{copy(locale, "Server guardrails stay authoritative.", "服务端强约束保持权威。")}</small></div>
              </div>
              <div className="agent-settings-guardrails">
                <strong>{copy(locale, "Server guardrails", "服务端强约束")}</strong>
                <div><span>{copy(locale, "Formal approval and hard Gate", "正式审批与 hard Gate")}</span><b>{copy(locale, "Locked", "后端锁定")}</b></div>
                <div><span>{copy(locale, "Authoritative fact and evidence writes", "权威事实与证据写入")}</span><b>{copy(locale, "Human confirmation", "人工确认")}</b></div>
                <div><span>{copy(locale, "Model provider and permission policy", "模型来源与权限策略")}</span><b>{copy(locale, "Server managed", "服务端管理")}</b></div>
                <div><span>{copy(locale, "Settings control plane", "设置控制面")}</span><b>{copy(locale, "Not an Agent", "非 Agent")}</b></div>
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </section>
  );
}
