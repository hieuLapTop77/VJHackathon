import { IconTrendUp, IconTrendDown, IconTrendNeutral, IconTrendMid } from "./icons";

const STATUS_CONFIG = {
  high: { cls: "success", icon: <IconTrendUp />,     label: "Increase"  },
  ok:   { cls: "info",    icon: <IconTrendNeutral />, label: "Optimize" },
  mid:  { cls: "warning", icon: <IconTrendMid />,    label: "Follow up" },
  low:  { cls: "danger",  icon: <IconTrendDown />,   label: "Increase"  },
};

export function StatusBadge({ status }) {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.ok;
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 4,
      padding: "2px 8px",
      borderRadius: 20,
      fontSize: 10,
      fontWeight: 500,
      background: `var(--color-background-${c.cls})`,
      color: `var(--color-text-${c.cls})`,
    }}>
      {c.icon}
      {c.label}
    </span>
  );
}
