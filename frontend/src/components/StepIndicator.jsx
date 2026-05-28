import { IconCheck } from "./icons";

export function StepDot({ num, label, active, done }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{
        width: 28, height: 28, borderRadius: "50%",
        background: done ? "var(--color-background-success)" : active ? "var(--color-background-info)" : "var(--color-background-secondary)",
        color: done ? "var(--color-text-success)" : active ? "var(--color-text-info)" : "var(--color-text-secondary)",
        border: `1px solid ${done ? "var(--color-border-success)" : active ? "var(--color-border-info)" : "var(--color-border-tertiary)"}`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 12, fontWeight: 600, transition: "all .2s",
      }}>
        {done ? <IconCheck /> : num}
      </div>
      <span style={{ fontSize: 12, fontWeight: active ? 600 : 400, color: active ? "var(--color-text-primary)" : "var(--color-text-secondary)" }}>
        {label}
      </span>
    </div>
  );
}

export function StepConnector({ done }) {
  return (
    <div style={{
      width: 40, height: 2,
      background: done ? "var(--color-border-success)" : "var(--color-border-tertiary)",
      borderRadius: 1, transition: "background .2s",
    }} />
  );
}
