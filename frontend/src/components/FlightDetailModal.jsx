import { useState, useEffect, useRef } from "react";
import { Spinner } from "./Spinner";
import { IconCheck } from "./icons";
import { fmt, fmtPct, getLFColor } from "../utils/formatters";

const FARE_FAMILY_COLORS = {
  "Eco": "#4CAF50",
  "Eco-Premium": "#2196F3",
  "SkyBoss": "#9C27B0",
  "Business": "#FF9800",
};

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

function validatePrice(price) {
  const num = parseFloat(price);
  if (isNaN(num) || num <= 0) return "Price must be > 0";
  if (num > 100_000_000) return "Price must be < 100M";
  return null;
}

export function FlightDetailModal({ flight, onClose, onSave }) {
  const [detail, setDetail]         = useState(null);
  const [loading, setLoading]       = useState(true);
  const [editedPrices, setEditedPrices] = useState({});
  const [saving, setSaving]         = useState(false);
  const [dragItem, setDragItem]     = useState(null);
  const [dragOverItem, setDragOverItem] = useState(null);
  const [fareFamilies, setFareFamilies] = useState([]);
  const [priceErrors, setPriceErrors] = useState({});
  const pricesRef = useRef({});

  useEffect(() => {
    if (!flight?.id) return;
    setLoading(true);
    setPriceErrors({});
    fetch(`${API}/flights/${flight.id}`)
      .then(r => r.json())
      .then(data => {
        setDetail(data);
        const prices = {};
        if (data.price) prices[data.id] = data.price;
        setEditedPrices(prices);
        pricesRef.current = { ...prices };
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [flight]);

  useEffect(() => {
    if (!flight?.flight_date) return;
    fetch(`${API}/flights?date_from=${flight.flight_date}&date_to=${flight.flight_date}&limit=50`)
      .then(r => r.json())
      .then(data => {
        const families = data.filter(f => f.route === flight.route);
        setFareFamilies(families);
        const prices = {};
        families.forEach(f => { prices[f.id] = f.price; });
        setEditedPrices(prices);
        pricesRef.current = prices;
      })
      .catch(() => {});
  }, [flight?.flight_date, flight?.route]);

  const handlePriceChange = (id, value) => {
    const newPrices = { ...editedPrices, [id]: value };
    setEditedPrices(newPrices);
    pricesRef.current = newPrices;
    setPriceErrors(prev => ({ ...prev, [id]: validatePrice(value) }));
  };

  const hasErrors = () => Object.values(priceErrors).some(e => e !== null);

  const handleSave = async () => {
    const errors = {};
    let hasAnyError = false;
    Object.entries(pricesRef.current).forEach(([id, price]) => {
      const err = validatePrice(price);
      if (err) { errors[id] = err; hasAnyError = true; }
    });
    setPriceErrors(errors);
    if (hasAnyError) return;

    setSaving(true);
    const updates = Object.entries(pricesRef.current).map(([id, price]) => ({
      id: parseInt(id),
      price: parseFloat(price) || 0,
    }));
    try {
      const res = await fetch(`${API}/flights/${flight.id}/fares`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates }),
      });
      if (res.ok) {
        const result = await res.json();
        onSave && onSave(result);
        onClose();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  // Drag handlers
  const handleDragStart = (e, idx) => { setDragItem(idx); e.dataTransfer.effectAllowed = "move"; };
  const handleDragOver  = (e, idx)  => { e.preventDefault(); setDragOverItem(idx); };
  const handleDrop     = (e, idx)  => {
    e.preventDefault();
    if (dragItem === null || dragItem === idx) return;
    const newFamilies = [...fareFamilies];
    const [moved] = newFamilies.splice(dragItem, 1);
    newFamilies.splice(idx, 0, moved);
    setFareFamilies(newFamilies);
    setDragItem(null);
    setDragOverItem(null);
  };
  const handleDragEnd = () => { setDragItem(null); setDragOverItem(null); };

  if (!flight) return null;

  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        background: "var(--color-background-primary)",
        borderRadius: "var(--border-radius-lg)",
        width: "90%", maxWidth: 700,
        maxHeight: "85vh",
        overflow: "hidden",
        display: "flex", flexDirection: "column",
      }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ padding: "16px 20px", borderBottom: "0.5px solid var(--color-border-tertiary)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>
              {flight.route || flight.flight_no} - {flight.flight_date}
            </div>
            <div style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: 2 }}>
              Flight details VJ | Drag to reorder priority
            </div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "var(--color-text-secondary)" }}>
            <i className="ti ti-x" />
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
          {loading ? (
            <Spinner />
          ) : (
            <>
              {/* Summary */}
              {detail && (
                <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
                  {[
                    { label: "Load Factor", value: `${Math.round(detail.lf * 100)}%`, color: getLFColor(detail.lf) },
                    { label: "Gia toi uu",   value: `${fmt(detail.optimal_price)} VND`, color: "var(--color-text-success)" },
                    { label: "Thay doi",     value: fmtPct(detail.price_change_pct), color: detail.price_change_pct > 0 ? "var(--color-text-danger)" : detail.price_change_pct < 0 ? "var(--color-text-success)" : "var(--color-text-info)" },
                  ].map(({ label, value, color }) => (
                    <div key={label} style={{ background: "var(--color-background-secondary)", borderRadius: 8, padding: "10px 14px", flex: 1 }}>
                      <div style={{ fontSize: 10, color: "var(--color-text-secondary)", textTransform: "uppercase" }}>{label}</div>
                      <div style={{ fontSize: 20, fontWeight: 600, fontFamily: "var(--font-mono)", color }}>
                        {value}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Fare families */}
              <div style={{ fontSize: 11, fontWeight: 500, marginBottom: 8, color: "var(--color-text-secondary)" }}>
                DANH SÁCH HẠNG VÉ ({fareFamilies.length} hạng)
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {fareFamilies.map((f, idx) => (
                  <div key={f.id}
                    draggable
                    onDragStart={e => handleDragStart(e, idx)}
                    onDragOver={e => handleDragOver(e, idx)}
                    onDrop={e => handleDrop(e, idx)}
                    onDragEnd={handleDragEnd}
                    style={{
                      background: dragOverItem === idx ? "var(--color-background-info)" : "var(--color-background-secondary)",
                      borderRadius: 8,
                      padding: "12px 14px",
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      border: "1px solid var(--color-border-tertiary)",
                      borderColor: dragItem === idx ? "var(--color-border-info)" : dragOverItem === idx ? "var(--color-border-success)" : "var(--color-border-tertiary)",
                      cursor: "grab",
                      opacity: dragItem === idx ? 0.5 : 1,
                      transition: "all .15s",
                    }}>
                    <div style={{ color: "var(--color-text-secondary)", fontSize: 16, cursor: "grab" }}>
                      <i className="ti ti-dots-vertical" />
                    </div>
                    <div style={{
                      padding: "4px 10px", borderRadius: 20, fontSize: 10, fontWeight: 600,
                      background: FARE_FAMILY_COLORS[f.fare_family] || "#666", color: "#fff", minWidth: 90, textAlign: "center",
                    }}>
                      {f.fare_family || "N/A"}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 10, color: "var(--color-text-secondary)", marginBottom: 3 }}>LF {Math.round(f.lf * 100)}%</div>
                      <div style={{ height: 4, background: "var(--color-border-tertiary)", borderRadius: 2, overflow: "hidden" }}>
                        <div style={{ width: Math.round(f.lf * 100) + "%", height: "100%", background: getLFColor(f.lf), borderRadius: 2 }} />
                      </div>
                    </div>
                    <div style={{ fontSize: 10, color: "var(--color-text-secondary)", minWidth: 80, textAlign: "right" }}>
                      Current Price
                      <div style={{ fontSize: 14, fontWeight: 600, fontFamily: "var(--font-mono)", color: "var(--color-text-secondary)" }}>{fmt(f.price)}</div>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <input
                          type="number"
                          value={editedPrices[f.id] || f.price}
                          onChange={e => handlePriceChange(f.id, e.target.value)}
                          style={{
                            width: 120, padding: "6px 10px", borderRadius: 6,
                            border: priceErrors[f.id] ? "0.5px solid var(--color-border-danger)" : "0.5px solid var(--color-border-info)",
                            background: "var(--color-background-primary)", color: "var(--color-text-primary)",
                            fontSize: 13, fontFamily: "var(--font-mono)", fontWeight: 500,
                          }}
                        />
                        <span style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>VND</span>
                      </div>
                      {priceErrors[f.id] && (
                        <div style={{ fontSize: 9, color: "var(--color-text-danger)" }}>{priceErrors[f.id]}</div>
                      )}
                    </div>
                    <div style={{
                      minWidth: 60, fontSize: 11, fontWeight: 600, fontFamily: "var(--font-mono)",
                      color: (editedPrices[f.id] || f.price) > f.price ? "var(--color-text-danger)"
                           : (editedPrices[f.id] || f.price) < f.price ? "var(--color-text-success)"
                           : "var(--color-text-secondary)",
                    }}>
                      {((editedPrices[f.id] || f.price) - f.price) >= 0 ? "+" : ""}
                      {fmt((editedPrices[f.id] || f.price) - f.price)}
                    </div>
                  </div>
                ))}
              </div>

              {fareFamilies.length === 0 && !loading && (
                <div style={{ textAlign: "center", padding: 24, color: "var(--color-text-secondary)" }}>
                  No fare information found
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "14px 20px", borderTop: "0.5px solid var(--color-border-tertiary)", display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button onClick={onClose} style={{
            padding: "8px 16px", borderRadius: 6, border: "0.5px solid var(--color-border-tertiary)",
            background: "transparent", color: "var(--color-text-secondary)", fontSize: 12, cursor: "pointer",
          }}>
            Close
          </button>
          <button onClick={handleSave} disabled={saving || hasErrors()} style={{
            padding: "8px 20px", borderRadius: 6, border: "none",
            background: saving ? "var(--color-background-secondary)" : hasErrors() ? "var(--color-background-secondary)" : "var(--color-background-success)",
            color: saving ? "var(--color-text-secondary)" : hasErrors() ? "var(--color-text-secondary)" : "var(--color-text-success)",
            fontSize: 12, fontWeight: 600, cursor: (saving || hasErrors()) ? "not-allowed" : "pointer",
            opacity: (saving || hasErrors()) ? 0.6 : 1,
          }}>
            {saving ? "Saving..." : hasErrors() ? "Please check prices" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
