import { useApi } from "../hooks/useApi";
import { fmt, fmtPct, getLFColor } from "../utils/formatters";
import { Spinner, ErrorBox } from "../components/Spinner";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";

export function RoutesPage() {
  const { data: routes, loading, error, refetch } = useApi("/routes");

  if (loading) return <Spinner />;
  if (error) return <div style={{ padding: 16 }}><ErrorBox msg={error} onRetry={refetch} /></div>;

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 17, fontWeight: 600 }}>Route Analytics</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 8 }}>
        {(routes || []).map(r => (
          <div key={r.route} style={{ background: "var(--color-background-secondary)", borderRadius: "var(--border-radius-lg)", padding: "12px 14px" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontWeight: 500, color: "var(--color-text-info)", fontSize: 13 }}>{r.route}</div>
            <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginBottom: 8 }}>{(r.count / 1000).toFixed(1)}K bookings</div>
            <div style={{ fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 2, textTransform: "uppercase", letterSpacing: ".04em" }}>Avg price</div>
            <div style={{ fontSize: 14, fontWeight: 500, fontFamily: "var(--font-mono)", marginBottom: 6 }}>{fmt(r.avg_price)}</div>
            <div style={{ height: 4, background: "var(--color-border-tertiary)", borderRadius: 2, marginBottom: 5 }}>
              <div style={{ width: Math.round(r.avg_lf * 100) + "%", height: "100%", background: getLFColor(r.avg_lf), borderRadius: 2 }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10 }}>
              <span style={{ color: "var(--color-text-secondary)" }}>LF {Math.round(r.avg_lf * 100)}%</span>
              <span style={{ color: r.revenue_delta_pct > 0 ? "var(--color-text-success)" : "var(--color-text-danger)" }}>
                {fmtPct(r.price_change_pct, 0)} → {fmtPct(r.revenue_delta_pct)}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ background: "var(--color-background-secondary)", borderRadius: "var(--border-radius-lg)", padding: "12px 14px" }}>
        <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 12 }}>Avg price by route</div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={routes || []} margin={{ left: 0, right: 0, top: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-tertiary)" vertical={false} />
            <XAxis dataKey="route" tick={{ fontSize: 10, fill: "var(--color-text-secondary)" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "var(--color-text-secondary)" }} axisLine={false} tickLine={false} tickFormatter={v => (v / 1e6).toFixed(1) + "M"} />
            <Tooltip contentStyle={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 8, fontSize: 11 }} formatter={v => [fmt(v) + " VND", "Avg price"]} />
            <Bar dataKey="avg_price" radius={[4, 4, 0, 0]}>
              {(routes || []).map((_, i) => <Cell key={i} fill={i % 2 === 0 ? "var(--color-background-info)" : "var(--color-border-info)"} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
