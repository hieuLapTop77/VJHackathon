import { NavLink, useLocation } from "react-router-dom";

const NAV = [
  { to: "/",          icon: "ti-chart-pie",             label: "Dashboard" },
  { to: "/overview",   icon: "ti-layout-dashboard",      label: "Overview"  },
  { to: "/optimizer",  icon: "ti-adjustments-horizontal", label: "Optimizer" },
  { to: "/simulator",  icon: "ti-chart-line",            label: "Simulator" },
  { to: "/routes",     icon: "ti-map-pin",               label: "Routes"    },
  { to: "/upload",     icon: "ti-upload",                label: "Upload"    },
];

export function Sidebar() {
  const location = useLocation();
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
      {NAV.map(n => {
        const isActive = n.to === "/" ? location.pathname === "/" : location.pathname.startsWith(n.to);
        return (
          <NavLink key={n.to} to={n.to} title={n.label}
            style={{
              width: 34, height: 34,
              borderRadius: "var(--border-radius-md)",
              border: "none",
              cursor: "pointer",
              fontSize: 15,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              textDecoration: "none",
              background: isActive ? "var(--color-background-info)" : "transparent",
              color: isActive ? "var(--color-text-info)" : "var(--color-text-secondary)",
              outline: isActive ? "1px solid var(--color-border-info)" : "none",
            }}>
            <i className={`ti ${n.icon}`} />
          </NavLink>
        );
      })}
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
