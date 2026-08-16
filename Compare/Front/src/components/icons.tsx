import type { SVGProps } from "react";
import type { DimensionId } from "../contracts/workbench";

export type IconName =
  | DimensionId
  | "material"
  | "recognition"
  | "business"
  | "risk"
  | "link"
  | "pdf"
  | "image"
  | "message"
  | "rule"
  | "robot"
  | "microphone"
  | "mcp"
  | "settings"
  | "chevron"
  | "expand"
  | "collapse"
  | "send";

export const dimensionColorVar: Record<DimensionId, string> = {
  compliance: "var(--dimension-compliance)",
  transaction: "var(--dimension-transaction)",
  production: "var(--dimension-production)",
  revenue: "var(--dimension-revenue)",
  debt: "var(--dimension-debt)",
  cashflow: "var(--dimension-cashflow)",
};

const iconPaths: Record<IconName, React.ReactNode> = {
  compliance: <><path d="M4.5 20.5V7.5h9v13" /><path d="m4.5 7.5 4.5-4 4.5 4M7.5 11h3M7.5 14h3M7.5 17h3" /><circle cx="17.5" cy="15.5" r="3" /><path d="m16.2 15.5.9.9 1.8-2" /></>,
  transaction: <><path d="M5 3.5h8l4 4v5M13 3.5v4h4M8 11h5M8 14h3.5M5 3.5v17h7" /><circle cx="16.5" cy="16.5" r="3.5" /><path d="m19 19 2 2" /></>,
  production: <><path d="M3.5 20.5v-9l5 2.5v-4l5 2.5V6h3v8l4 2v4.5z" /><path d="M6.5 17.5h2M11 17.5h2M15.5 17.5h2" /><path d="M16.5 6V3.5h2V6" /></>,
  revenue: <><path d="M4 20V5M4 20h16" /><path d="m7 16 4-4 3 2 5-6" /><path d="M16 8h3v3" /></>,
  debt: <><path d="M12 3.5 19 6v5.1c0 4.6-2.8 7.9-7 9.4-4.2-1.5-7-4.8-7-9.4V6z" /><circle cx="12" cy="11" r="3" /><path d="M10.5 10h3M10.5 12h3" /></>,
  cashflow: <><path d="M12 3.5 19 6v5.1c0 4.6-2.8 7.9-7 9.4-4.2-1.5-7-4.8-7-9.4V6z" /><path d="m8.7 11.8 2.1 2.1 4.6-5" /></>,
  material: <><path d="M6 3.5h8l4 4V20.5H6z" /><path d="M14 3.5v4h4M9 12h6M9 15.5h6" /></>,
  recognition: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 15V9h2.5a2 2 0 0 1 0 4H8m7-4v6m0-6 2 6 2-6" /></>,
  business: <><circle cx="12" cy="8" r="3" /><path d="M5.5 20v-2.5A4.5 4.5 0 0 1 10 13h4a4.5 4.5 0 0 1 4.5 4.5V20" /></>,
  risk: <><path d="M12 3 19 6v5.2c0 4.5-2.8 7.8-7 9.3-4.2-1.5-7-4.8-7-9.3V6z" /><path d="M9 12h6M12 9v6" /></>,
  link: <><path d="m9.5 14.5-1 1a3 3 0 0 1-4.2-4.2l3-3a3 3 0 0 1 4.2 0" /><path d="m14.5 9.5 1-1a3 3 0 1 1 4.2 4.2l-3 3a3 3 0 0 1-4.2 0M8.5 15.5l7-7" /></>,
  pdf: <><path d="M5 3.5h10l4 4V20.5H5z" /><path d="M15 3.5v4h4" /><path d="M8 15v-4h2a1.5 1.5 0 0 1 0 3H8m5-3v4h1a2 2 0 0 0 0-4zm4 4v-4h2" /></>,
  image: <><rect x="3.5" y="4" width="17" height="16" rx="2" /><circle cx="9" cy="9" r="1.5" /><path d="m5.5 17 4.5-4 3 2 2.5-3 3 5" /></>,
  message: <path d="M4 5.5h16v11H9l-4.5 3v-3H4z" />,
  rule: <><path d="M6 3.5h12v17H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></>,
  robot: <><rect x="5" y="7" width="14" height="11" rx="3" /><path d="M12 4v3M9 12h.01M15 12h.01M9 15h6" /></>,
  microphone: <><rect x="9" y="3.5" width="6" height="11" rx="3" /><path d="M6.5 11.5a5.5 5.5 0 0 0 11 0M12 17v3M9 20h6" /></>,
  mcp: <><circle cx="6" cy="6" r="2" /><circle cx="18" cy="6" r="2" /><circle cx="12" cy="18" r="2" /><path d="m7.7 7.1 3.1 8.8M16.3 7.1l-3.1 8.8M8 6h8" /></>,
  settings: <><path d="M9.6 3.6h4.8l.5 2.1 1.8 1 2.1-.6 2.4 4.1-1.6 1.5v2.1l1.6 1.5-2.4 4.1-2.1-.6-1.8 1-.5 2.1H9.6l-.5-2.1-1.8-1-2.1.6-2.4-4.1 1.6-1.5v-2.1l-1.6-1.5 2.4-4.1 2.1.6 1.8-1z" /><circle cx="12" cy="12" r="3.1" /></>,
  chevron: <path d="m9 7 5 5-5 5" />,
  expand: <><path d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5" /></>,
  collapse: <><path d="M4 9h5V4M20 9h-5V4M4 15h5v5M20 15h-5v5" /></>,
  send: <><path d="m4 4 16 8-16 8 3-8z" /><path d="M7 12h13" /></>,
};

const industryProcessPaths: Record<string, React.ReactNode> = {
  装备制造: <><circle cx="12" cy="12" r="3.2" /><path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3M6 6l2.1 2.1M15.9 15.9 18 18M18 6l-2.1 2.1M8.1 15.9 6 18" /></>,
  纺织服装: <><path d="M7 4.5h10l-1.8 15H8.8zM9.5 8h5M9 12h6M8.5 16h7" /><path d="M5 7.5h2M17 7.5h2" /></>,
  食品加工: <><path d="M12 20.5V5M12 8c-3 0-4-1.5-4.5-3.5C10.5 4.5 12 6 12 8Zm0 4c-3 0-4-1.5-4.5-3.5C10.5 8.5 12 10 12 12Zm0 4c-3 0-4-1.5-4.5-3.5C10.5 12.5 12 14 12 16ZM12 8c3 0 4-1.5 4.5-3.5C13.5 4.5 12 6 12 8Zm0 4c3 0 4-1.5 4.5-3.5C13.5 8.5 12 10 12 12Zm0 4c3 0 4-1.5 4.5-3.5C13.5 12.5 12 14 12 16Z" /></>,
  物流运输: <><path d="M3.5 7h10v10h-10zM13.5 10h4l3 3v4h-7z" /><circle cx="7" cy="18" r="2" /><circle cx="17" cy="18" r="2" /></>,
  医疗服务: <><path d="M9 4.5h6V9h4.5v6H15v4.5H9V15H4.5V9H9z" /></>,
  新能源: <><path d="M18.5 4.5C11 5 6.5 9.2 6.5 14.5c0 3 2 5 5 5 5.3 0 7-6.4 7-15Z" /><path d="M5 20c2.6-5.6 6-8.5 10.5-11.5" /><path d="m11.5 11.5-1 3h2.4l-1.2 3.5" /></>,
};

export function Icon({ name, ...props }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      focusable="false"
      height="20"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.65"
      viewBox="0 0 24 24"
      width="20"
      {...props}
    >
      {iconPaths[name]}
    </svg>
  );
}

export function IndustryProcessIcon({ industry, ...props }: { industry: string } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      focusable="false"
      height="20"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.6"
      viewBox="0 0 24 24"
      width="20"
      {...props}
    >
      {industryProcessPaths[industry] ?? industryProcessPaths.装备制造}
    </svg>
  );
}
