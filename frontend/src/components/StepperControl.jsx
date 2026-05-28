import { IconPlus, IconMinus } from "./icons";
import { fmt } from "../utils/formatters";

export function StepperControl({ label, value, onChange, min, max, step, unit, icon }) {
  const stepVal = step || 1;
  const displayVal = unit === "VND" ? fmt(value) : String(value);
  const unitSuffix = unit === "VND" ? " VND" : unit ? ` ${unit}` : "";

  return (
    <div style={{
      background: "var(--color-background-secondary)",
      borderRadius: 12, padding: "16px 18px",
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {icon && <span style={{ color: "var(--color-text-secondary)", display: "flex" }}>{icon}</span>}
          <span style={{ fontSize: 11, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", fontWeight: 500 }}>
            {label}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={() => onChange(Math.max(min, value - stepVal))}
            disabled={value <= min}
            style={{
              width: 30, height: 30, borderRadius: 8,
              border: "0.5px solid var(--color-border-tertiary)",
              background: value <= min ? "transparent" : "var(--color-background-primary)",
              color: value <= min ? "var(--color-border-tertiary)" : "var(--color-text-primary)",
              cursor: value <= min ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 14, fontWeight: 600, transition: "all .1s",
            }}
          >
            <IconMinus />
          </button>

          <div style={{
            minWidth: 90, textAlign: "center",
            fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 600,
            color: "var(--color-text-primary)",
          }}>
            {displayVal}{unitSuffix}
          </div>

          <button
            onClick={() => onChange(Math.min(max, value + stepVal))}
            disabled={value >= max}
            style={{
              width: 30, height: 30, borderRadius: 8,
              border: "0.5px solid var(--color-border-tertiary)",
              background: value >= max ? "transparent" : "var(--color-background-primary)",
              color: value >= max ? "var(--color-border-tertiary)" : "var(--color-text-primary)",
              cursor: value >= max ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 14, fontWeight: 600, transition: "all .1s",
            }}
          >
            <IconPlus />
          </button>
        </div>
      </div>
      <input
        type="range" min={min} max={max} step={stepVal} value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: "100%" }}
      />
    </div>
  );
}
