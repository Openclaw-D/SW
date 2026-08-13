import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import type { LocalMaterialStatus } from "../contracts/workbench";

export function Button({ className = "", variant = "ghost", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "ghost" | "outline" | "primary" }) {
  return <button className={`ui-button ui-button-${variant} ${className}`} type="button" {...props} />;
}

export function Tag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "simulated" | "attention" | "success" }) {
  return <span className={`ui-tag ui-tag-${tone}`}>{children}</span>;
}

export function StatusMark({ status, label }: { status: LocalMaterialStatus; label?: string }) {
  const glyph: Record<LocalMaterialStatus, string> = {
    confirmed: "✓",
    review: "?",
    conflict: "×",
  };
  return <span aria-label={label ?? status} className={`status-mark status-${status}`}>{glyph[status]}</span>;
}

export function Panel({ className = "", children, ...props }: HTMLAttributes<HTMLElement> & { children: ReactNode }) {
  return <section className={`ui-panel ${className}`} {...props}>{children}</section>;
}

export function Divider({ vertical = false }: { vertical?: boolean }) {
  return <span aria-hidden="true" className={vertical ? "ui-divider is-vertical" : "ui-divider"} />;
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state" role="status">
      <span className="empty-state-dot" />
      <div><strong>{title}</strong><small>{detail}</small></div>
    </div>
  );
}
