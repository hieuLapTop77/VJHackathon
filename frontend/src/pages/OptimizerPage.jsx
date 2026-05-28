import { useState, useEffect, useCallback, useRef } from "react";
import { useApi } from "../hooks/useApi";
import { fmt, fmtPct } from "../utils/formatters";
import { StepperControl } from "../components/StepperControl";
import { Spinner } from "../components/Spinner";
import { SortToggle } from "../components/SortToggle";
import { IconCheck, IconWarning, IconChevronUp, IconChevronDown, IconArrowRight, IconDollar, IconUsers, IconSearch, IconRefresh, IconMapPin, IconCalendar, IconSort } from "../components/icons";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const PAGE_SIZE = 50;

const ENSEMBLE_STRATEGIES = [
  { id: "average",       label: "Average",       desc: "Simple mean of all 6 models" },
  { id: "weighted_perf", label: "Weighted",     desc: "Inverse-MAPE weighted (default)" },
  { id: "top3",          label: "Top 3",        desc: "Best 3 models by MAPE" },
];

function StrategyBadge({ strategy, active, onClick }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", fontWeight: 500 }}>
        Ensemble Strategy
      </span>
      <div style={{ display: "flex", gap: 6 }}>
        {ENSEMBLE_STRATEGIES.map(s => (
          <button key={s.id} onClick={() => onClick(s.id)}
            style={{
              padding: "4px 12px",
              borderRadius: 20,
              border: "0.5px solid",
              fontSize: 11,
              cursor: "pointer",
              fontWeight: active === s.id ? 700 : 400,
              borderColor: active === s.id ? "var(--color-border-info)" : "var(--color-border-tertiary)",
              background: active === s.id ? "var(--color-background-info)" : "transparent",
              color: active === s.id ? "var(--color-text-info)" : "var(--color-text-secondary)",
              transition: "all .15s",
            }}
            title={s.desc}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ModelRow({ name, prediction, mape, isBest, isSelected, onClick }) {
  return (
    <div onClick={onClick}
      style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "7px 10px",
        borderRadius: 8,
        background: isSelected ? "var(--color-background-info)" : "var(--color-background-tertiary)",
        cursor: "pointer",
        border: `0.5px solid ${isSelected ? "var(--color-border-info)" : "transparent"}`,
        transition: "all .1s",
      }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{
          fontSize: 11,
          fontWeight: isBest ? 700 : 500,
          color: isSelected ? "var(--color-text-info)" : "var(--color-text-secondary)",
        }}>
          {name}
        </span>
        {isBest && (
          <span style={{
            background: "var(--color-background-success)",
            color: "var(--color-text-success)",
            fontSize: 9, padding: "1px 5px",
            borderRadius: 10, fontWeight: 600,
          }}>
            Best
          </span>
        )}
      </div>
      <span style={{
        fontSize: 12, fontFamily: "var(--font-mono)",
        color: isSelected ? "var(--color-text-info)" : "var(--color-text-secondary)",
        fontWeight: 600,
      }}>
        {prediction != null ? `${fmt(prediction)} VND` : "--"}
      </span>
    </div>
  );
}

export function OptimizerPage({ selectedFlight }) {
  const today = new Date().toISOString().split("T")[0];

  const [filters, setFilters] = useState({
    dep: "", arr: "", flight_date: today, sort_by: "flight_date", sort_dir: "asc",
  });
  const [flights, setFlights]       = useState([]);
  const [flLoading, setFlLoading]  = useState(false);
  const [flError, setFlError]     = useState(null);
  const [page, setPage]           = useState(1);
  const { data: flightsRaw, refetch: refetchFlights } = useApi("/flights");
  const { data: dbRoutes } = useApi("/db/routes");
  const { data: modelsData } = useApi("/models");

  const [curFlight, setCurFlight]      = useState(null);
  const [strategy, setStrategy]        = useState("weighted_perf");
  const [lf, setLf]                   = useState(38);
  const [price, setPrice]             = useState(1283740);
  const [optResult, setOptResult]      = useState(null);
  const [ensembleResult, setEnsembleResult] = useState(null);
  const [individualPreds, setIndividualPreds] = useState(null);
  const [optLoading, setOptLoading]    = useState(false);
  const [predLoading, setPredLoading]  = useState(false);
  const [applyStatus, setApplyStatus] = useState(null);

  const optDebounceRef  = useRef(null);
  const predDebounceRef = useRef(null);

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

  // Auto-search when filters change
  useEffect(() => {
    const fetchFlights = async () => {
      setFlLoading(true);
      setFlError(null);
      try {
        const res = await fetch(`${API}/flights?${buildQs()}`);
        if (!res.ok) throw new Error(`API error ${res.status}`);
        const data = await res.json();
        if (Array.isArray(data)) {
          setFlights(data);
        } else if (data.items) {
          setFlights(data.items);
        } else if (data.data) {
          setFlights(data.data);
        } else {
          setFlights([]);
        }
      } catch (e) {
        setFlError(e.message);
      } finally {
        setFlLoading(false);
      }
    };
    fetchFlights();
  }, [filters.dep, filters.arr, filters.flight_date, filters.sort_by, filters.sort_dir, page]);

  const handleSortChange = (label, direction) => {
    const map = { "Date": "flight_date", "Price": "price", "LF": "lf", "Route": "route" };
    setFilter("sort_by", map[label] || label);
    setFilter("sort_dir", direction);
  };

  const handleReset = () => {
    setFilters({ dep: "", arr: "", flight_date: today, sort_by: "flight_date", sort_dir: "asc" });
    setPage(1);
  };

  useEffect(() => {
    if (selectedFlight) {
      setCurFlight(selectedFlight);
      setLf(Math.round(selectedFlight.lf * 100));
      setPrice(selectedFlight.price);
      setOptResult(null);
      setEnsembleResult(null);
    }
  }, [selectedFlight]);

  useEffect(() => {
    if (curFlight) {
      clearTimeout(predDebounceRef.current);
      predDebounceRef.current = setTimeout(() => {
        callEnsemblePrediction(curFlight, lf, strategy);
      }, 600);
    }
  }, [curFlight, lf, strategy]);

  const callEnsemblePrediction = useCallback(async (flight, currentLf, currentStrategy) => {
    if (!flight) return;
    setPredLoading(true);
    try {
      const [dep, arr] = (flight.route || "").split("->");
      const body = {
        lead_time_days: 15,
        LF_by_date: currentLf / 100,
        LF_by_fare: currentLf / 100,
        booking_velocity_3d: 0.02,
        booking_velocity_7d: 0.05,
        Weekday: 4,
        IsHoliday: 0,
        is_oneway: 1,
        lng_fuel: 93.86,
        capacity: 230,
        count_sked: 3,
        fare_family: "Eco",
        fare_category: "B  ",
        dep: dep || "SGN",
        arr: arr || "HAN",
        strategy: currentStrategy,
      };
      const res = await fetch(`${API}/predict-ensemble`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const data = await res.json();
        setEnsembleResult(data);
        setIndividualPreds(data.individual_predictions || {});
      }
    } catch (e) {
      console.error("Ensemble prediction failed:", e);
    } finally {
      setPredLoading(false);
    }
  }, []);

  const callOptimize = useCallback(async (p, l) => {
    setOptLoading(true);
    try {
      const res = await fetch(`${API}/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_price: p, base_lf: l / 100, capacity: 230 }),
      });
      setOptResult(await res.json());
    } finally {
      setOptLoading(false);
    }
  }, []);

  const onControlChange = (newPrice, newLf) => {
    setLf(newLf);
    setPrice(newPrice);
    clearTimeout(optDebounceRef.current);
    optDebounceRef.current = setTimeout(() => {
      callOptimize(newPrice, newLf);
    }, 400);
  };

  const selectFlight = (f) => {
    setCurFlight(f);
    setLf(Math.round(f.lf * 100));
    setPrice(f.price);
    setOptResult(null);
    setEnsembleResult(null);
  };

  const applyPrice = useCallback(async () => {
    if (!curFlight) return;
    setApplyStatus("saving");
    try {
      const res = await fetch(`${API}/flights/${curFlight.id}/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ applied_price: price }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setApplyStatus("ok");
      setTimeout(() => setApplyStatus(null), 3000);
    } catch {
      setApplyStatus("error");
      setTimeout(() => setApplyStatus(null), 3000);
    }
  }, [curFlight, price]);

  const optColor = optResult
    ? optResult.price_change_pct > 0 ? "var(--color-text-success)"
      : optResult.price_change_pct < 0 ? "var(--color-text-danger)"
      : "var(--color-text-info)"
    : "var(--color-text-primary)";

  const bestModel = modelsData?.models?.find(m => m.best);

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

      {/* Header + strategy selector */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 17, fontWeight: 600 }}>Price Optimizer</span>
          <span style={{ background: "var(--color-background-info)", color: "var(--color-text-info)", padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 500 }}>
            Optimizer Mode
          </span>
          {bestModel && (
            <span style={{ background: "var(--color-background-success)", color: "var(--color-text-success)", padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 500 }}>
              MAPE {bestModel.mape?.toFixed(1)}%
            </span>
          )}
        </div>
        <StrategyBadge strategy={strategy} active={strategy} onClick={setStrategy} />
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
            {[...new Set((dbRoutes || []).map(r => r.str_Dep || r.route?.split("-")[0]).filter(Boolean))].map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 130 }}>
          <label style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", display: "flex", alignItems: "center", gap: 4 }}>
            <IconMapPin /> Arrival
          </label>
          <select value={filters.arr} onChange={e => setFilter("arr", e.target.value)}
            style={{ padding: "6px 10px", borderRadius: 8, border: "0.5px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", color: "var(--color-text-primary)", fontSize: 12 }}>
            <option value="">All airports</option>
            {[...new Set((dbRoutes || []).map(r => r.str_Arr || r.route?.split("-")[1]).filter(Boolean))].map(a => <option key={a} value={a}>{a}</option>)}
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
        <button onClick={() => setPage(1)} disabled={flLoading}
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

      {/* Flight list */}
      <div style={{ background: "var(--color-background-secondary)", borderRadius: 12, overflow: "hidden", border: "0.5px solid var(--color-border-tertiary)", maxHeight: 200, overflowY: "auto" }}>
        <div style={{ padding: "8px 12px", borderBottom: "0.5px solid var(--color-border-tertiary)", display: "flex", justifyContent: "space-between", alignItems: "center", position: "sticky", top: 0, background: "var(--color-background-secondary)", zIndex: 1 }}>
          <span style={{ fontSize: 11, fontWeight: 500 }}>Available flights</span>
          <span style={{ fontSize: 10, color: "var(--color-text-secondary)" }}>{flights.length} flights</span>
        </div>
        {flLoading && <div style={{ padding: 16, textAlign: "center" }}><Spinner /></div>}
        {!flLoading && flights.length === 0 && (
          <div style={{ padding: "12px 16px", textAlign: "center", color: "var(--color-text-secondary)", fontSize: 11 }}>
            No flights found. Please change filters or upload data.
          </div>
        )}
        {!flLoading && flights.length > 0 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", padding: "8px 12px" }}>
            {flights.map(f => (
              <button key={f.id} onClick={() => selectFlight(f)}
                style={{
                  padding: "4px 12px", borderRadius: 8, border: "0.5px solid",
                  fontSize: 11, cursor: "pointer",
                  borderColor: curFlight?.id === f.id ? "var(--color-border-info)" : "var(--color-border-tertiary)",
                  background: curFlight?.id === f.id ? "var(--color-background-info)" : "transparent",
                  color: curFlight?.id === f.id ? "var(--color-text-info)" : "var(--color-text-secondary)",
                  fontFamily: "var(--font-mono)", fontWeight: curFlight?.id === f.id ? 600 : 400,
                }}>
                {f.flight_no || f.id} {f.route ? `· ${f.route}` : ""}
              </button>
            ))}
          </div>
        )}
        {flights.length > PAGE_SIZE && (
          <div style={{ padding: "6px 12px", borderTop: "0.5px solid var(--color-border-tertiary)", display: "flex", justifyContent: "center" }}>
            <button onClick={() => setPage(p => Math.min(p + 1, Math.ceil(flights.length / PAGE_SIZE)))}
              style={{ fontSize: 10, color: "var(--color-text-info)", background: "none", border: "none", cursor: "pointer" }}>
              Load more ({Math.min(PAGE_SIZE, flights.length - (page - 1) * PAGE_SIZE)} / {flights.length})
            </button>
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, flex: 1 }}>

        {/* LEFT: Controls */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{
            background: "var(--color-background-secondary)",
            borderRadius: 12, padding: "14px 16px",
            border: "0.5px solid var(--color-border-info)",
          }}>
            <div style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 4 }}>
              Chuyen dang chon
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, fontFamily: "var(--font-mono)", color: "var(--color-text-info)" }}>
              {curFlight ? `${curFlight.flight_no || curFlight.id} · ${curFlight.route || "--"}` : "--"}
            </div>
            {curFlight && (
              <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
                <div>
                  <div style={{ fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 2 }}>Current Price</div>
                  <div style={{ fontSize: 14, fontFamily: "var(--font-mono)", fontWeight: 600 }}>{fmt(curFlight.price || 0)} VND</div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 2 }}>Load Factor</div>
                  <div style={{ fontSize: 14, fontFamily: "var(--font-mono)", fontWeight: 600 }}>{Math.round((curFlight.lf || 0) * 100)}%</div>
                </div>
              </div>
            )}
          </div>

          <StepperControl
            label="Load Factor"
            value={lf}
            onChange={v => onControlChange(price, v)}
            min={10} max={100} step={1} unit="%"
            icon={<IconUsers />}
          />

          <StepperControl
            label="Gia ve"
            value={price}
            onChange={v => onControlChange(v, lf)}
            min={200000} max={5000000} step={50000} unit="VND"
            icon={<IconDollar />}
          />
        </div>

        {/* RIGHT: Results */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

          {/* Ensemble prediction result */}
          <div style={{
            background: "var(--color-background-secondary)",
            borderRadius: 12, padding: "16px 18px",
            border: "1px solid var(--color-border-info)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 6 }}>
                  Ensemble Prediction
                </div>
                <div style={{ fontSize: 28, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--color-text-info)" }}>
                  {predLoading ? "--" : ensembleResult ? fmt(ensembleResult.predicted_price_vnd) : "--"} VND
                </div>
                {predLoading && (
                  <div style={{ marginTop: 6, fontSize: 11, color: "var(--color-text-secondary)", display: "flex", alignItems: "center", gap: 4 }}>
                    <i className="ti ti-loader" style={{ animation: "spin 1s linear infinite" }} /> Running ensemble...
                  </div>
                )}
                {ensembleResult && !predLoading && (
                  <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: 4 }}>
                    Strategy: <strong>{strategy === "average" ? "Simple Average" : strategy === "weighted_perf" ? "Weighted by Performance" : "Top 3 Models"}</strong>
                    {" · "}
                    {Object.keys(individualPreds || {}).length} models
                  </div>
                )}
              </div>
              {ensembleResult && !predLoading && (
                <div style={{
                  background: "var(--color-background-info)",
                  borderRadius: 10, padding: "6px 12px",
                  fontSize: 11, fontFamily: "var(--font-mono)",
                  color: "var(--color-text-info)",
                }}>
                  {strategy === "average" && `6 models average`}
                  {strategy === "weighted_perf" && "MAPE-weighted"}
                  {strategy === "top3" && "Top 3 only"}
                </div>
              )}
            </div>
          </div>

          {/* Elasticity optimal */}
          <div style={{
            background: "var(--color-background-secondary)",
            borderRadius: 12, padding: "16px 18px",
            border: "1px solid var(--color-border-info)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 6 }}>
                  Gia toi uu (Elasticity)
                </div>
                <div style={{ fontSize: 28, fontWeight: 700, fontFamily: "var(--font-mono)", color: optColor }}>
                  {optLoading ? "--" : optResult ? fmt(optResult.optimal_price) : "--"} VND
                </div>
                {optResult && !optLoading && (
                  <div style={{ fontSize: 12, color: "var(--color-text-secondary)", marginTop: 6, display: "flex", alignItems: "center", gap: 4 }}>
                    {optResult.price_change_pct > 0
                      ? <span style={{ color: "var(--color-text-success)", display: "flex", alignItems: "center", gap: 2 }}><IconChevronUp /> Increase</span>
                      : optResult.price_change_pct < 0
                      ? <span style={{ color: "var(--color-text-danger)", display: "flex", alignItems: "center", gap: 2 }}><IconChevronDown /> Decrease</span>
                      : <span style={{ color: "var(--color-text-info)" }}>{'\u2192'} No change</span>}
                    {" "}{fmtPct(optResult.price_change_pct)} · LF {Math.round(optResult.optimal_lf * 100)}%
                  </div>
                )}
              </div>
              {optResult && !optLoading && (
                <div style={{
                  background: optResult.revenue_delta_pct >= 0 ? "var(--color-background-success)" : "var(--color-background-danger)",
                  color: optResult.revenue_delta_pct >= 0 ? "var(--color-text-success)" : "var(--color-text-danger)",
                  borderRadius: 10, padding: "6px 12px", fontSize: 14, fontWeight: 700,
                  fontFamily: "var(--font-mono)", textAlign: "center",
                }}>
                  {fmtPct(optResult.revenue_delta_pct)}
                  <div style={{ fontSize: 9, fontWeight: 400, marginTop: 2 }}>Revenue</div>
                </div>
              )}
            </div>
          </div>

          {/* Revenue delta + LF */}
          {optResult && !optLoading && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div style={{ background: "var(--color-background-secondary)", borderRadius: 10, padding: "12px 14px" }}>
                <div style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 4 }}>Revenue delta</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-mono)", color: optResult.revenue_delta_pct >= 0 ? "var(--color-text-success)" : "var(--color-text-danger)" }}>
                  {fmtPct(optResult.revenue_delta_pct)}
                </div>
              </div>
              <div style={{ background: "var(--color-background-secondary)", borderRadius: 10, padding: "12px 14px" }}>
                <div style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 4 }}>LF du bao</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--color-text-info)" }}>
                  {Math.round(optResult.optimal_lf * 100)}%
                </div>
              </div>
            </div>
          )}

          {/* AI recommendation */}
          {optResult && optResult.recommendation && !optLoading && (
            <div style={{
              borderLeft: "3px solid var(--color-border-info)",
              padding: "12px 14px",
              background: "var(--color-background-info)",
              borderRadius: "0 10px 10px 0",
            }}>
              <div style={{ fontSize: 10, color: "var(--color-text-info)", marginBottom: 4, fontWeight: 600, display: "flex", alignItems: "center", gap: 4 }}>
                <IconCheck /> AI Recommendation
              </div>
              <div style={{ fontSize: 12, color: "var(--color-text-secondary)", lineHeight: 1.7 }}>
                {optResult.recommendation}
              </div>
            </div>
          )}

          {/* Individual model predictions */}
          {individualPreds && modelsData?.models && !predLoading && (
            <div style={{ background: "var(--color-background-secondary)", borderRadius: 12, padding: "14px 16px" }}>
              <div style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 10 }}>
                6 Models Comparison
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {modelsData.models.map(m => {
                  const pred = individualPreds[m.name];
                  return (
                    <div key={m.name} style={{
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      padding: "5px 8px",
                      borderRadius: 6,
                      background: "var(--color-background-tertiary)",
                      fontSize: 11,
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontWeight: m.best ? 700 : 400, color: "var(--color-text-secondary)" }}>{m.name}</span>
                        {m.best && <span style={{ fontSize: 9, background: "var(--color-background-success)", color: "var(--color-text-success)", padding: "0 4px", borderRadius: 8, fontWeight: 600 }}>Best</span>}
                        <span style={{ color: "var(--color-text-secondary)", fontSize: 10 }}>MAPE {m.mape?.toFixed(1)}%</span>
                      </div>
                      <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--color-text-secondary)" }}>
                        {pred?.prediction != null ? fmt(pred.prediction) : "--"} VND
                      </span>
                    </div>
                  );
                })}
              </div>
              {ensembleResult?.all_strategies && (
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: "0.5px solid var(--color-border-tertiary)", display: "flex", flexDirection: "column", gap: 4 }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "var(--color-text-info)", textTransform: "uppercase", letterSpacing: ".04em" }}>
                    Ensemble Results
                  </div>
                  {Object.entries(ensembleResult.all_strategies).map(([key, val]) => (
                    <div key={key} style={{
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      padding: "4px 8px",
                      borderRadius: 6,
                      background: key === strategy ? "var(--color-background-info)" : "transparent",
                      border: key === strategy ? "0.5px solid var(--color-border-info)" : "none",
                      fontSize: 11,
                    }}>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <span style={{ fontWeight: key === strategy ? 700 : 400, color: key === strategy ? "var(--color-text-info)" : "var(--color-text-secondary)" }}>
                          {key === "average" ? "Average" : key === "weighted_perf" ? "Weighted" : "Top 3"}
                        </span>
                        {key === strategy && <span style={{ fontSize: 9, color: "var(--color-text-info)", fontWeight: 600 }}>Active</span>}
                      </div>
                      <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--color-text-info)" }}>
                        {fmt(val.predicted_price_vnd)} VND
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Apply button */}
          <button
            onClick={applyPrice}
            disabled={applyStatus === "saving" || !curFlight}
            style={{
              padding: "12px 0", borderRadius: 10, border: "none",
              background: applyStatus === "ok"
                ? "var(--color-background-success)"
                : applyStatus === "error"
                ? "var(--color-background-danger)"
                : !curFlight
                ? "var(--color-background-secondary)"
                : "var(--color-background-info)",
              color: applyStatus === "ok"
                ? "var(--color-text-success)"
                : applyStatus === "error"
                ? "var(--color-text-danger)"
                : !curFlight
                ? "var(--color-text-secondary)"
                : "var(--color-text-info)",
              fontSize: 13, fontWeight: 700,
              cursor: (!curFlight || applyStatus === "saving") ? "not-allowed" : "pointer",
              opacity: (!curFlight || applyStatus === "saving") ? 0.5 : 1,
              display: "flex", alignItems: "center", justifyContent: "center",
              gap: 6, transition: "all .2s", marginTop: "auto",
            }}
          >
            {applyStatus === "saving" && <><i className="ti ti-loader" style={{ animation: "spin 1s linear infinite" }} /> Dang luu...</>}
            {applyStatus === "ok"     && <><IconCheck /> Saved successfully!</>}
            {applyStatus === "error"  && <><IconWarning /> Error! Try again</>}
            {!applyStatus && curFlight && <><IconCheck /> Apply price {fmt(price)} VND for flight {curFlight.flight_no || curFlight.id}</>}
            {!applyStatus && !curFlight && "Select a flight to apply"}
          </button>
        </div>
      </div>
    </div>
  );
}
