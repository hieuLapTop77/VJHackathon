const NAV = [
  { id: "overview",  icon: "ti-layout-dashboard",      label: "Overview"  },
  { id: "optimizer", icon: "ti-adjustments-horizontal", label: "Optimizer" },
  { id: "simulator", icon: "ti-chart-line",            label: "Simulator" },
  { id: "routes",    icon: "ti-map-pin",               label: "Routes"    },
  { id: "upload",    icon: "ti-upload",                 label: "Upload"    },
];

export function Sidebar({ active, onNav }) {
  return (
    <div style={{
      width: 48,
      background: "var(--color-background-secondary)",
      borderRight: "0.5px solid var(--color-border-tertiary)",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      padding: "12px 0",
      gap: 2,
      flexShrink: 0,
    }}>
      <i className="ti ti-plane" style={{ fontSize: 18, color: "var(--color-text-info)", marginBottom: 14 }} />
      {NAV.map(n => (
        <button key={n.id} onClick={() => onNav(n.id)} title={n.label}
          style={{
            width: 34, height: 34,
            borderRadius: "var(--border-radius-md)",
            border: "none",
            cursor: "pointer",
            fontSize: 15,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: active === n.id ? "var(--color-background-info)" : "transparent",
            color: active === n.id ? "var(--color-text-info)" : "var(--color-text-secondary)",
            outline: active === n.id ? "1px solid var(--color-border-info)" : "none",
          }}>
          <i className={`ti ${n.icon}`} />
        </button>
      ))}
      <div style={{ flex: 1 }} />
      <div style={{
        width: 26, height: 26, borderRadius: "50%",
        background: "var(--color-background-info)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 10, color: "var(--color-text-info)", marginBottom: 8,
      }}>
        AI
      </div>
    </div>
  );
}
