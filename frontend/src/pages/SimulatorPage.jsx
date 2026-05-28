import { useState, useCallback, useEffect } from "react";
import { useApi } from "../hooks/useApi";
import { fmt, fmtPct } from "../utils/formatters";
import { Spinner } from "../components/Spinner";
import { IconMapPin, IconCalendar, IconSearch, IconRefresh, IconArrowRight } from "../components/icons";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from "recharts";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function SimulatorPage() {
  const today = new Date().toISOString().split("T")[0];
  const [filters, setFilters] = useState({
    dep: "", arr: "", flight_date: today,
  });
  const { data: routes } = useApi("/routes");
  const [simRoute, setSimRoute] = useState(null);
  const [pct, setPct]         = useState(0);
  const [simData, setSimData] = useState(null);
  const [loading, setLoading]  = useState(false);

  const loadSim = useCallback(async (route) => {
    if (!route) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_price: route.avg_price, base_lf: route.avg_lf, capacity: 230, from_pct: -30, to_pct: 50 }),
      });
      setSimData(await res.json());
    } finally { setLoading(false); }
  }, []);

  const setFilter = (key, val) => setFilters(prev => ({ ...prev, [key]: val }));

  const handleReset = () => {
    setFilters({ dep: "", arr: "", flight_date: today });
  };

  const filteredRoutes = (routes || []).filter(r => {
    const dep = r.route?.split("-")[0] || "";
    const arr = r.route?.split("-")[1] || "";
    if (filters.dep && dep !== filters.dep) return false;
    if (filters.arr && arr !== filters.arr) return false;
    return true;
  });

  useEffect(() => {
    if (filteredRoutes.length > 0 && !filteredRoutes.find(r => r.route === simRoute?.route)) {
      setSimRoute(filteredRoutes[0]);
      setPct(0);
      loadSim(filteredRoutes[0]);
    }
  }, [filters.dep, filters.arr, filteredRoutes.length]);

  const currentPoint = simData?.find(d => Math.abs(d.price_change_pct - pct) <= 2.6);
  const optPoint = simData?.reduce((best, d) =>
    d.revenue_delta_pct > (best?.revenue_delta_pct ?? -Infinity) ? d : best, null);

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 17, fontWeight: 600 }}>Revenue Simulator</span>
          <span style={{ background: "var(--color-background-warning)", color: "var(--color-text-warning)", padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 500 }}>
            What-if Mode
          </span>
        </div>
      </div>

      {/* Filter bar */}
      <div style={{ background: "var(--color-background-secondary)", borderRadius: "var(--border-radius-lg)", padding: "10px 14px", display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 130 }}>
          <label style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", display: "flex", alignItems: "center", gap: 4 }}>
            <IconMapPin /> Departure
          </label>
          <select value={filters.dep} onChange={e => setFilter("dep", e.target.value)}
            style={{ padding: "6px 10px", borderRadius: 8, border: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", color: "var(--color-text-primary)", fontSize: 12 }}>
            <option value="">All airports</option>
            {[...new Set((routes || []).map(r => r.route?.split("-")[0]).filter(Boolean))].map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 130 }}>
          <label style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", display: "flex", alignItems: "center", gap: 4 }}>
            <IconMapPin /> Arrival
          </label>
          <select value={filters.arr} onChange={e => setFilter("arr", e.target.value)}
            style={{ padding: "6px 10px", borderRadius: 8, border: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", color: "var(--color-text-primary)", fontSize: 12 }}>
            <option value="">All airports</option>
            {[...new Set((routes || []).map(r => r.route?.split("-")[1]).filter(Boolean))].map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 140 }}>
          <label style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", display: "flex", alignItems: "center", gap: 4 }}>
            <IconCalendar /> Flight Date
          </label>
          <input type="date" value={filters.flight_date} onChange={e => setFilter("flight_date", e.target.value)}
            style={{ padding: "6px 10px", borderRadius: 8, border: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", color: "var(--color-text-primary)", fontSize: 12 }} />
        </div>
        <div style={{ flex: 1 }} />
        <button onClick={handleReset}
          style={{ padding: "8px 12px", borderRadius: 8, border: "0.5px solid var(--color-border-tertiary)",
            background: "transparent", color: "var(--color-text-secondary)", fontSize: 12, cursor: "pointer",
            display: "flex", alignItems: "center", gap: 6, height: 36 }}>
          <IconRefresh /> Reset
        </button>
      </div>

      {/* Route selector */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>Route:</span>
        {filteredRoutes.length === 0 && (
          <span style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>No routes match filters</span>
        )}
        {filteredRoutes.map(r => (
          <button key={r.route} onClick={() => { setSimRoute(r); setPct(0); loadSim(r); }}
            style={{
              padding: "4px 10px", borderRadius: 20, border: "0.5px solid",
              fontSize: 11, cursor: "pointer",
              borderColor: simRoute?.route === r.route ? "var(--color-border-info)" : "var(--color-border-tertiary)",
              background: simRoute?.route === r.route ? "var(--color-background-info)" : "transparent",
              color: simRoute?.route === r.route ? "var(--color-text-info)" : "var(--color-text-secondary)",
            }}>
            {r.route}
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 12, flex: 1 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ background: "var(--color-background-secondary)", borderRadius: "var(--border-radius-lg)", padding: "10px 12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 5, textTransform: "uppercase", letterSpacing: ".04em" }}>
              <span>Price Change</span>
              <span style={{ fontFamily: "var(--font-mono)", color: pct > 0 ? "var(--color-text-danger)" : pct < 0 ? "var(--color-text-success)" : "var(--color-text-primary)", fontWeight: 500 }}>
                {pct >= 0 ? "+" : ""}{pct}%
              </span>
            </div>
            <input type="range" min={-30} max={50} step={1} value={pct} onChange={e => setPct(+e.target.value)} style={{ width: "100%" }} />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--color-text-secondary)", marginTop: 3 }}>
              <span>-30%</span><span>0</span><span>+50%</span>
            </div>
          </div>
          {[
            { label: "New Price", val: simRoute ? fmt(Math.round(simRoute.avg_price * (1 + pct / 100))) + " VND" : "--" },
            { label: "Revenue Delta", val: currentPoint ? fmtPct(currentPoint.revenue_delta_pct) : "--", color: currentPoint?.revenue_delta_pct >= 0 ? "var(--color-text-success)" : "var(--color-text-danger)" },
            { label: "LF Predicted", val: currentPoint ? Math.round(currentPoint.new_lf * 100) + "%" : "--", color: "var(--color-text-info)" },
          ].map(s => (
            <div key={s.label} style={{ background: "var(--color-background-secondary)", borderRadius: "var(--border-radius-md)", padding: "8px 10px" }}>
              <div style={{ fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 3, textTransform: "uppercase", letterSpacing: ".04em" }}>{s.label}</div>
              <div style={{ fontSize: 14, fontWeight: 500, fontFamily: "var(--font-mono)", color: s.color || "var(--color-text-primary)" }}>{s.val}</div>
            </div>
          ))}
          {optPoint && (
            <div style={{ background: "var(--color-background-success)", borderRadius: "var(--border-radius-md)", padding: "8px 10px" }}>
              <div style={{ fontSize: 10, color: "var(--color-text-success)", marginBottom: 3 }}>* Optimal point</div>
              <div style={{ fontSize: 14, fontWeight: 500, color: "var(--color-text-success)", fontFamily: "var(--font-mono)" }}>{fmtPct(optPoint.price_change_pct, 0)}</div>
              <div style={{ fontSize: 11, color: "var(--color-text-success)" }}>Revenue Delta {fmtPct(optPoint.revenue_delta_pct)}</div>
            </div>
          )}
        </div>

        <div style={{ background: "var(--color-background-secondary)", borderRadius: "var(--border-radius-lg)", padding: "12px 14px", display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 2 }}>Revenue Curve -- {simRoute?.route}</div>
          <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginBottom: 10 }}>
            {simRoute ? `Base ${fmt(simRoute.avg_price)} VND . LF ${Math.round(simRoute.avg_lf * 100)}%` : ""}
          </div>
          {loading && <Spinner />}
          {simData && !loading && (
            <div style={{ flex: 1, minHeight: 200 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={simData} margin={{ left: 10, right: 10, top: 5, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-tertiary)" />
                  <XAxis dataKey="price_change_pct" tick={{ fontSize: 10, fill: "var(--color-text-secondary)" }} tickFormatter={v => v + "%"} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: "var(--color-text-secondary)" }} axisLine={false} tickLine={false} tickFormatter={v => v.toFixed(0) + "%"} />
                  <Tooltip contentStyle={{ background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)", borderRadius: 8, fontSize: 11 }} />
                  <ReferenceLine x={0} stroke="var(--color-border-secondary)" strokeDasharray="4 3" />
                  {optPoint && <ReferenceLine x={optPoint.price_change_pct} stroke="var(--color-border-success)" strokeDasharray="4 3" label={{ value: "Opt", fill: "var(--color-text-success)", fontSize: 10 }} />}
                  <ReferenceLine x={pct} stroke="var(--color-border-info)" strokeWidth={1.5} label={{ value: "v", fill: "var(--color-text-info)", fontSize: 12, position: "top" }} />
                  <Line type="monotone" dataKey="revenue_delta_pct" stroke="var(--color-border-info)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="new_lf" stroke="var(--color-border-warning)" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          <div style={{ display: "flex", gap: 14, marginTop: 8 }}>
            {[["var(--color-border-info)", "Revenue d (%)"], ["var(--color-border-warning)", "Load factor"], ["var(--color-border-success)", "Optimal"]].map(([c, l]) => (
              <div key={l} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--color-text-secondary)" }}>
                <div style={{ width: 14, height: 2, background: c }} />{l}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
