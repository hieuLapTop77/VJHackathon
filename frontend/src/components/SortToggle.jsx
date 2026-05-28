import { IconChevronUp, IconChevronDown } from "./icons";

export function SortToggle({ label, active, direction, onClick }) {
  const isActive = active === label;
  return (
    <button
      onClick={() => onClick(label, isActive ? (direction === "asc" ? "desc" : "asc") : "desc")}
      title={`Sort by ${label}`}
      style={{
        display: "flex", alignItems: "center", gap: 4,
        padding: "4px 10px", borderRadius: 6,
        border: `0.5px solid ${isActive ? "var(--color-border-info)" : "var(--color-border-tertiary)"}`,
        background: isActive ? "var(--color-background-info)" : "transparent",
        color: isActive ? "var(--color-text-info)" : "var(--color-text-secondary)",
        fontSize: 11, cursor: "pointer",
        fontWeight: isActive ? 500 : 400,
        transition: "all .15s", whiteSpace: "nowrap",
      }}
    >
      {label}
      <span style={{ display: "flex", flexDirection: "column", gap: 1, marginLeft: 2 }}>
        <span style={{
          color: (isActive && direction === "asc") ? "var(--color-text-info)" : "var(--color-text-secondary)",
          opacity: (isActive && direction === "asc") ? 1 : 0.4, lineHeight: 1,
        }}>
          <IconChevronUp />
        </span>
        <span style={{
          color: (isActive && direction === "desc") ? "var(--color-text-info)" : "var(--color-text-secondary)",
          opacity: (isActive && direction === "desc") ? 1 : 0.4, lineHeight: 1,
        }}>
          <IconChevronDown />
        </span>
      </span>
    </button>
  );
}
