import { useState, useRef } from "react";
import { IconRefresh, IconWarning, IconCheck } from "../components/icons";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

function FileDropZone({ file, onFileChange, onReset }) {
  const fileRef = useRef();
  const [dragging, setDragging] = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) onFileChange(f);
  };

  return (
    <div
      onDrop={handleDrop}
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onClick={() => !file && fileRef.current?.click()}
      style={{
        border: `1.5px dashed ${dragging ? "var(--color-border-info)" : file ? "var(--color-border-success)" : "var(--color-border-info)"}`,
        borderRadius: 12,
        padding: "20px 16px",
        textAlign: "center",
        cursor: file ? "default" : "pointer",
        background: file ? "var(--color-background-success)" : "var(--color-background-secondary)",
        transition: "all .2s",
        minHeight: 160,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
      }}
    >
      <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls"
        style={{ display: "none" }} onChange={e => e.target.files?.[0] && onFileChange(e.target.files[0])} />
      {file ? (
        <>
          <IconCheck />
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text-success)" }}>{file.name}</div>
          <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>{(file.size / 1024).toFixed(1)} KB</div>
          <button onClick={e => { e.stopPropagation(); onReset(); }}
            style={{ marginTop: 4, padding: "4px 12px", borderRadius: 6, border: "0.5px solid var(--color-border-tertiary)", background: "transparent", color: "var(--color-text-secondary)", fontSize: 11, cursor: "pointer" }}>
            Change file
          </button>
        </>
      ) : (
        <>
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none" stroke="var(--color-text-info)" strokeWidth="1.5">
            <rect x="4" y="2" width="20" height="24" rx="2"/>
            <path d="M9 2v8M19 2v8M4 14h20M4 19h20"/>
          </svg>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)" }}>Drop file here</div>
          <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>CSV or Excel (.csv, .xlsx, .xls)</div>
        </>
      )}
    </div>
  );
}

export function UploadPage({ onGoToOverview }) {
  const [file, setFile]       = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]  = useState(null);

  const hasFile   = !!file;
  const hasResult2 = !!result;
  const hasError2  = !!error;

  const handleFileChange = (f) => {
    setFile(f);
    setResult(null);
    setError(null);
  };

  const handleReset = () => {
    setFile(null);
    setResult(null);
    setError(null);
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(`${API}/flights/upload`, { method: "POST", body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setResult({
        rows_inserted: data.rows_inserted || 0,
        rows_updated: data.rows_updated || 0,
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGoToOverview = () => {
    if (onGoToOverview) onGoToOverview();
  };

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 17, fontWeight: 600 }}>Upload Data</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 16, flex: 1, minHeight: 0 }}>

        {/* LEFT: Actions */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <FileDropZone file={file} onFileChange={handleFileChange} onReset={handleReset} />

          {hasFile && !hasResult2 && (
            <button onClick={handleUpload} disabled={loading}
              style={{
                padding: "11px 0", borderRadius: 10, border: "none",
                background: loading ? "var(--color-background-secondary)" : "var(--color-background-info)",
                color: loading ? "var(--color-text-secondary)" : "var(--color-text-info)",
                fontSize: 13, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.6 : 1, display: "flex", alignItems: "center",
                justifyContent: "center", gap: 8, transition: "all .2s",
              }}>
              {loading
                ? <><i className="ti ti-loader" style={{ animation: "spin 1s linear infinite" }} /> Processing...</>
                : <><IconCheck /> Insert Database</>}
            </button>
          )}

          {hasResult2 && (
            <button onClick={handleGoToOverview}
              style={{
                padding: "11px 0", borderRadius: 10, border: "none",
                background: "var(--color-background-info)",
                color: "var(--color-text-info)",
                fontSize: 13, fontWeight: 700, cursor: "pointer",
                display: "flex", alignItems: "center",
                justifyContent: "center", gap: 8,
              }}>
              <IconCheck /> Xem ket qua o Overview
            </button>
          )}

          {hasResult2 && (
            <button onClick={handleReset}
              style={{
                padding: "9px 0", borderRadius: 10,
                border: "0.5px solid var(--color-border-tertiary)",
                background: "transparent", color: "var(--color-text-secondary)",
                fontSize: 12, cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
              }}>
              <IconRefresh /> Upload another file
            </button>
          )}

          <div style={{
            background: "var(--color-background-secondary)",
            borderRadius: 10, padding: "12px 14px",
            fontSize: 11, color: "var(--color-text-secondary)", lineHeight: 1.8,
          }}>
            <div style={{ fontWeight: 600, color: "var(--color-text-primary)", marginBottom: 6, fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em" }}>
              Cau truc file
            </div>
            <div style={{ marginBottom: 4 }}>
              <span style={{ color: "var(--color-text-info)", fontWeight: 500 }}>Cot bat buoc:</span>
              <div style={{ marginTop: 3, paddingLeft: 8, borderLeft: "2px solid var(--color-border-info)" }}>
                dtm_Local_ETD_Date, str_Dep, str_Arr, str_Fare_Category_Ident, mny_GL_Charges_Total, LF_by_date
              </div>
            </div>
            <div>
              <span style={{ color: "var(--color-text-secondary)", fontWeight: 500 }}>Cot tuy chon:</span>
              <div style={{ marginTop: 3, paddingLeft: 8, borderLeft: "2px solid var(--color-border-tertiary)" }}>
                lead_time_days, booking_velocity_3d/7d, Weekday, IsHoliday, lng_Capacity, lng_fuel, fare_family
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT: Results */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12, overflow: "auto" }}>
          {hasError2 && (
            <div style={{ padding: "12px 16px", background: "var(--color-background-danger)", borderRadius: 12, color: "var(--color-text-danger)", fontSize: 12, display: "flex", alignItems: "flex-start", gap: 8, lineHeight: 1.6 }}>
              <IconWarning />
              <div>
                <div style={{ fontWeight: 600, marginBottom: 2 }}>Loi xay ra!</div>
                <div>{error}</div>
              </div>
            </div>
          )}

          {result && (
            <>
              <div style={{
                padding: "10px 14px",
                borderRadius: 10,
                background: "var(--color-background-success)",
                color: "var(--color-text-success)",
                fontSize: 12,
                fontWeight: 600,
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}>
                <IconCheck />
                <span>Da insert {result.rows_inserted} dong moi, cap nhat {result.rows_updated} dong!</span>
              </div>

              <div style={{
                flex: 1, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", gap: 16, padding: "32px 20px",
                background: "var(--color-background-secondary)", borderRadius: 12,
                border: "0.5px solid var(--color-border-tertiary)", textAlign: "center",
              }}>
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="var(--color-text-success)" strokeWidth="1.5">
                  <circle cx="24" cy="24" r="20"/>
                  <path d="M16 24l6 6 12-12"/>
                </svg>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)", marginBottom: 6 }}>Upload thanh cong!</div>
                  <div style={{ fontSize: 12, color: "var(--color-text-secondary)", lineHeight: 1.7 }}>
                    Data da duoc insert vao SQL Server.<br />
                    Chuyen sang trang Overview de xem ket qua predict.
                  </div>
                </div>
              </div>
            </>
          )}

          {!hasFile && !hasResult2 && !hasError2 && (
            <div style={{
              flex: 1, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 16, padding: "32px 20px",
              background: "var(--color-background-secondary)", borderRadius: 12,
              border: "0.5px solid var(--color-border-tertiary)", textAlign: "center",
            }}>
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="var(--color-text-secondary)" strokeWidth="1.2">
                <rect x="6" y="4" width="36" height="40" rx="3"/>
                <path d="M14 4v14M34 4v14M6 26h36M6 34h36"/>
              </svg>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)", marginBottom: 6 }}>Chua co file</div>
                <div style={{ fontSize: 12, color: "var(--color-text-secondary)", lineHeight: 1.7, maxWidth: 360 }}>
                  Upload file Excel/CSV de insert data vao SQL Server.
                </div>
              </div>
            </div>
          )}

          {loading && (
            <div style={{
              flex: 1, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 12, padding: "48px 20px",
              background: "var(--color-background-secondary)", borderRadius: 12,
              border: "0.5px solid var(--color-border-tertiary)", textAlign: "center",
            }}>
              <div style={{ fontSize: 28, color: "var(--color-text-info)", animation: "spin 1s linear infinite" }}>
                <i className="ti ti-loader" />
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)" }}>Dang upload...</div>
              <div style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>Vui long cho...</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
