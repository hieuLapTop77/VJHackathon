import { useState, useEffect, useCallback } from "react";
import { useApi } from "../hooks/useApi";
import { fmt, fmtM, fmtPct } from "../utils/formatters";
import { Spinner, ErrorBox, LfBar } from "../components/Spinner";
import { StatusBadge } from "../components/StatusBadge";
import { SortToggle } from "../components/SortToggle";
import { Pagination } from "../components/Pagination";
import { FlightDetailModal } from "../components/FlightDetailModal";
import { IconSearch, IconRefresh, IconMapPin, IconCalendar, IconSort, IconDollar, IconUsers, IconArrowRight, IconChevronUp, IconChevronDown } from "../components/icons";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

const PAGE_SIZE = 15;

const FARE_FAMILY_COLORS = {
  "Eco": "#4CAF50", "Eco-Premium": "#2196F3",
  "SkyBoss": "#9C27B0", "Business": "#FF9800",
};

export function OverviewPage({ onSelectFlight }) {
  const today = new Date().toISOString().split("T")[0];

  const [filters, setFilters] = useState({
    dep: "", arr: "", flight_date: today, sort_by: "flight_date", sort_dir: "asc",
  });
  const [flights, setFlights]       = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [flLoading, setFlLoading]  = useState(false);
  const [flError, setFlError]     = useState(null);
  const [selectedFlight, setSelectedFlight] = useState(null);
  const [page, setPage]           = useState(1);

  const summaryQs = `?dep=${encodeURIComponent(filters.dep)}&arr=${encodeURIComponent(filters.arr)}&flight_date=${encodeURIComponent(filters.flight_date)}`;
  const { data: summary, loading: sl, error: se, refetch: sr } = useApi(`/summary${summaryQs}`);
  const { data: dbRoutes } = useApi("/db/routes");

  const setFilter = (key, val) => {
    setFilters(prev => ({ ...prev, [key]: val }));
    setPage(1);
  };

  const buildQs = () => {
    const p = new URLSearchParams();
    if (filters.dep)        p.set("dep", filters.dep);
    if (filters.arr)        p.set("arr", filters.arr);
    if (filters.flight_date) p.set("flight_date", filters.flight_date);
    if (filters.sort_by)    p.set("sort_by", filters.sort_by);
    if (filters.sort_dir)   p.set("sort_dir", filters.sort_dir);
    p.set("page", page);
    p.set("page_size", PAGE_SIZE);
    return p.toString();
  };

  const handleSearch = useCallback(async () => {
    setFlLoading(true);
    setFlError(null);
    try {
      const res = await fetch(`${API}/flights?${buildQs()}`);
      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data = await res.json();
      if (Array.isArray(data)) {
        setFlights(data);
        setTotalCount(data.length);
      } else if (data.items) {
        setFlights(data.items);
        setTotalCount(data.total ?? data.items.length);
      } else if (data.data) {
        setFlights(data.data);
        setTotalCount(data.total ?? data.data.length);
      } else {
        setFlights([]);
        setTotalCount(0);
      }
    } catch (e) {
      setFlError(e.message);
    } finally {
      setFlLoading(false);
    }
  }, [filters.dep, filters.arr, filters.flight_date, filters.sort_by, filters.sort_dir, page]);

  useEffect(() => { handleSearch(); }, [handleSearch]);

  const handleSortChange = (label, direction) => {
    const map = { "Date": "flight_date", "Price": "price", "LF": "lf", "Route": "route" };
    setFilter("sort_by", map[label] || label);
    setFilter("sort_dir", direction);
  };

  const handleFlightClick = (f) => {
    setSelectedFlight(f);
    onSelectFlight && onSelectFlight(f);
  };

  const handleModalClose = () => { setSelectedFlight(null); handleSearch(); };

  const handleReset = () => {
    setFilters({ dep: "", arr: "", flight_date: today, sort_by: "flight_date", sort_dir: "asc" });
    setPage(1);
  };

  const deps = [...new Set((dbRoutes || []).map(r => r.str_Dep || r.route?.split("-")[0]).filter(Boolean))];
  const arrs = [...new Set((dbRoutes || []).map(r => r.str_Arr || r.route?.split("-")[1]).filter(Boolean))];
  const totalFlights = totalCount;

  if (sl && !summary) return <Spinner />;

  return (
    <>
      <div style={{ flex: 1, overflow: "auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 17, fontWeight: 600 }}>List of flights</span>
            <span style={{ background: "var(--color-background-success)", color: "var(--color-text-success)", padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 500, display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--color-text-success)" }} />
              Live data
            </span>
          </div>
          <span style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>{filters.flight_date || today}</span>
        </div>

        {se && <ErrorBox msg={se} onRetry={sr} />}
        {flError && <ErrorBox msg={flError} onRetry={handleSearch} />}

        {/* Filter bar */}
        <div style={{ background: "var(--color-background-secondary)", borderRadius: "var(--border-radius-lg)", padding: "10px 14px", display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 130 }}>
            <label style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", display: "flex", alignItems: "center", gap: 4 }}>
              <IconMapPin /> Departure
            </label>
            <select value={filters.dep} onChange={e => setFilter("dep", e.target.value)}
              style={{ padding: "6px 10px", borderRadius: 8, border: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", color: "var(--color-text-primary)", fontSize: 12 }}>
              <option value="">All airports</option>
              {deps.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 130 }}>
            <label style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", display: "flex", alignItems: "center", gap: 4 }}>
              <IconMapPin /> Arrival
            </label>
            <select value={filters.arr} onChange={e => setFilter("arr", e.target.value)}
              style={{ padding: "6px 10px", borderRadius: 8, border: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", color: "var(--color-text-primary)", fontSize: 12 }}>
              <option value="">All airports</option>
              {arrs.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 140 }}>
            <label style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", display: "flex", alignItems: "center", gap: 4 }}>
              <IconCalendar /> Flight Date
            </label>
            <input type="date" value={filters.flight_date} onChange={e => setFilter("flight_date", e.target.value)}
              style={{ padding: "6px 10px", borderRadius: 8, border: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", color: "var(--color-text-primary)", fontSize: 12 }} />
          </div>
          <div style={{ width: "0.5px", height: 36, background: "var(--color-border-tertiary)", margin: "0 2px", alignSelf: "center" }} />
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", display: "flex", alignItems: "center", gap: 4 }}>
              <IconSort /> Sort by
            </label>
            <div style={{ display: "flex", gap: 4 }}>
              {["Date", "Price", "LF", "Route"].map(l => (
                <SortToggle key={l} label={l}
                  active={filters.sort_by === { Date: "flight_date", Price: "price", LF: "lf", Route: "route" }[l] ? l : null}
                  direction={filters.sort_dir} onClick={handleSortChange}
                />
              ))}
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <button onClick={() => { setPage(1); handleSearch(); }} disabled={flLoading}
            style={{ padding: "8px 16px", borderRadius: 8, border: "none",
              background: flLoading ? "var(--color-background-secondary)" : "var(--color-background-info)",
              color: flLoading ? "var(--color-text-secondary)" : "var(--color-text-info)",
              fontSize: 12, fontWeight: 600, cursor: flLoading ? "not-allowed" : "pointer",
              opacity: flLoading ? 0.6 : 1, display: "flex", alignItems: "center", gap: 6, height: 36 }}>
            <IconSearch /> {flLoading ? "Searching..." : "Search"}
          </button>
          <button onClick={handleReset}
            style={{ padding: "8px 12px", borderRadius: 8, border: "0.5px solid var(--color-border-tertiary)",
              background: "transparent", color: "var(--color-text-secondary)", fontSize: 12, cursor: "pointer",
              display: "flex", alignItems: "center", gap: 6, height: 36 }}>
            <IconRefresh /> Reset
          </button>
        </div>

        {/* Summary stats */}
        {summary && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10, opacity: sl ? 0.6 : 1, transition: "opacity 0.15s ease-in-out" }}>
            {[
              { label: "Load factor TB", value: `${Math.round(summary.avg_load_factor * 100)}%`, sub: "average" },
              { label: "Can toi uu", value: `${summary.flights_need_action} / ${summary.flights_total}`, sub: "flights need to adjust", color: "var(--color-text-warning)" },
            ].map(({ label, value, sub, color }, i) => (
              <div key={label} style={{ background: "var(--color-background-secondary)", borderRadius: 10, padding: "12px 14px" }}>
                <div style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 6, display: "flex", alignItems: "center", gap: 4 }}>
                  {label === "Load factor TB" && <IconUsers />}
                  {label}
                </div>
                <div style={{ fontSize: 20, fontWeight: 600, fontFamily: "var(--font-mono)", color: color || undefined }}>
                  <span key={value} className="number-change-pulse">{value}</span>
                </div>
                <div style={{ fontSize: 10, color: color || "var(--color-text-secondary)", marginTop: 3 }}>{sub}</div>
              </div>
            ))}
          </div>
        )}

        {/* Flights table */}
        <div style={{ border: "0.5px solid var(--color-border-tertiary)", borderRadius: 12, overflow: "hidden", background: "var(--color-background-secondary)" }}>
          <div style={{ padding: "10px 14px", borderBottom: "0.5px solid var(--color-border-tertiary)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, fontWeight: 500 }}>List of flights</span>
            <span style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>
              {flLoading ? "Loading..." : totalFlights ? `${totalFlights} flights` : "--"}
            </span>
          </div>

          {flLoading && <div style={{ padding: 32, textAlign: "center" }}><Spinner /></div>}
          {!flLoading && (!flights || flights.length === 0) && (
            <div style={{ padding: "24px 16px", textAlign: "center", color: "var(--color-text-secondary)", fontSize: 12 }}>
              No flights found. Please change filters or upload data.
            </div>
          )}
          {!flLoading && flights && flights.length > 0 && (
            <>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: "0.5px solid var(--color-border-tertiary)" }}>
                      {["Flight", "Flight Date", "Route", "Fare Family", "LF", "Current Price", "AI Suggestion", "Status"].map(h => (
                        <th key={h} style={{ padding: "7px 10px", color: "var(--color-text-secondary)", fontWeight: 500, textAlign: "left", fontSize: 10, textTransform: "uppercase", letterSpacing: ".04em", whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {flights.map(f => (
                      <tr key={f.id}
                        onClick={() => handleFlightClick(f)}
                        style={{ borderBottom: "0.5px solid var(--color-border-tertiary)", cursor: "pointer", transition: "background .1s" }}
                        onMouseEnter={e => e.currentTarget.style.background = "var(--color-background-tertiary)"}
                        onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                        <td style={{ padding: "9px 10px", fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--color-text-info)", fontSize: 12 }}>{f.flight_no || f.id}</td>
                        <td style={{ padding: "9px 10px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-text-secondary)" }}>{f.flight_date || "--"}</td>
                        <td style={{ padding: "9px 10px", fontSize: 12 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                            <span style={{ fontWeight: 500 }}>{f.route?.split("->")[0] || "--"}</span>
                            <IconArrowRight />
                            <span style={{ fontWeight: 500 }}>{f.route?.split("->")[1] || ""}</span>
                          </div>
                        </td>
                        <td style={{ padding: "9px 10px" }}>
                          <span style={{ padding: "2px 8px", borderRadius: 12, fontSize: 10, fontWeight: 600, background: FARE_FAMILY_COLORS[f.fare_family] || "#666", color: "#fff", display: "inline-block" }}>
                            {f.fare_family || f.fare_category || "--"}
                          </span>
                        </td>
                        <td style={{ padding: "9px 10px" }}><LfBar lf={f.lf} /></td>
                        <td style={{ padding: "9px 10px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--color-text-secondary)" }}>{fmt(f.price || 0)}</td>
                        <td style={{ padding: "9px 10px", fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: 12, color: f.price_change_pct > 0 ? "var(--color-text-success)" : f.price_change_pct < 0 ? "var(--color-text-danger)" : "var(--color-text-info)" }}>
                          {f.price_change_pct > 0 ? <IconChevronUp /> : f.price_change_pct < 0 ? <IconChevronDown /> : <IconArrowRight />} {fmt(f.optimal_price || 0)}
                        </td>

                        <td style={{ padding: "9px 10px" }}><StatusBadge status={f.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ padding: "10px 14px", borderTop: "0.5px solid var(--color-border-tertiary)", display: "flex", justifyContent: "flex-end" }}>
                <Pagination page={page} total={totalFlights} pageSize={PAGE_SIZE} onChange={p => setPage(p)} />
              </div>
            </>
          )}
        </div>
      </div>

      {selectedFlight && (
        <FlightDetailModal flight={selectedFlight} onClose={handleModalClose} onSave={() => {}} />
      )}
    </>
  );
}
