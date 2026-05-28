export function Spinner() {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: 32, color: "var(--color-text-secondary)", fontSize: 12,
    }}>
      <i className="ti ti-loader" style={{ fontSize: 20, marginRight: 8, animation: "spin 1s linear infinite" }} />
      Dang tai tu API...
    </div>
  );
}

export function ErrorBox({ msg, onRetry }) {
  return (
    <div style={{
      padding: "12px 16px",
      background: "var(--color-background-danger)",
      borderRadius: "var(--border-radius-md)",
      color: "var(--color-text-danger)",
      fontSize: 12,
    }}>
      <i className="ti ti-alert-circle" style={{ marginRight: 6 }} />
      {msg}
      {onRetry && (
        <button onClick={onRetry} style={{
          marginLeft: 12, fontSize: 11, cursor: "pointer",
          background: "none",
          border: "0.5px solid var(--color-border-danger)",
          borderRadius: 4, padding: "2px 8px",
          color: "var(--color-text-danger)",
        }}>
          Retry
        </button>
      )}
    </div>
  );
}

export function StatCard({ label, value, delta, deltaUp, sub }) {
  return (
    <div style={{
      background: "var(--color-background-secondary)",
      borderRadius: "var(--border-radius-md)",
      padding: "10px 12px", flex: 1, minWidth: 0,
    }}>
      <div style={{
        fontSize: 10, color: "var(--color-text-secondary)",
        textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 4,
      }}>
        {label}
      </div>
      <div style={{ fontSize: 18, fontWeight: 500, fontFamily: "var(--font-mono)", marginBottom: 2 }}>
        {value}
      </div>
      {delta && (
        <div style={{ fontSize: 11, color: deltaUp ? "var(--color-text-success)" : "var(--color-text-danger)" }}>
          {deltaUp ? "^" : "v"} {delta}
        </div>
      )}
      {sub && <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>{sub}</div>}
    </div>
  );
}

function _getLFColor(lf) {
  return lf > 0.7 ? "var(--color-background-success)"
    : lf > 0.5 ? "var(--color-background-warning)"
    : "var(--color-background-danger)";
}

export function LfBar({ lf, height = 4 }) {
  const pct = Math.round((lf || 0) * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <div style={{ width: 40, height, background: "var(--color-border-tertiary)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: pct + "%", height: "100%", background: _getLFColor(lf), borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--color-text-secondary)" }}>
        {pct}%
      </span>
    </div>
  );
}
