import { useState } from "react";
import { useApi } from "./hooks/useApi";
import { Sidebar } from "./components/Sidebar";
import { OverviewPage } from "./pages/OverviewPage";
import { OptimizerPage } from "./pages/OptimizerPage";
import { SimulatorPage } from "./pages/SimulatorPage";
import { RoutesPage } from "./pages/RoutesPage";
import { UploadPage } from "./pages/UploadPage";
import { IconPlane } from "./components/icons";

export default function App() {
  const [page, setPage]           = useState("overview");
  const [selectedFlight, setFlight] = useState(null);
  const { data: health }          = useApi("/health");
  const { data: modelsData }      = useApi("/models");

  function handleSelectFlight(f) {
    setFlight(f);
    setPage("optimizer");
  }

  const bestModel = modelsData?.models?.find(m => m.best);
  const mapeLabel = bestModel?.mape != null ? `MAPE ${bestModel.mape.toFixed(2)}%` : null;
  const r2Label   = bestModel?.r2 != null ? `R2 ${bestModel.r2.toFixed(4)}` : null;

  return (
    <div style={{
      display: "flex", height: "100vh",
      background: "var(--color-background-tertiary)",
      fontFamily: "var(--font-sans)", overflow: "hidden",
    }}>
      <Sidebar active={page} onNav={setPage} />

      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Top bar */}
        <div style={{
          height: 40,
          borderBottom: "0.5px solid var(--color-border-tertiary)",
          display: "flex", alignItems: "center",
          padding: "0 16px", gap: 8, flexShrink: 0,
          background: "var(--color-background-secondary)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ color: "var(--color-text-info)", display: "flex" }}><IconPlane /></span>
            <span style={{ fontSize: 13, fontWeight: 700 }}>Airline Revenue</span>
          </div>
          <span style={{ color: "var(--color-border-secondary)" }}>|</span>
          <span style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>
            {modelsData ? `6 models | Best: ${bestModel?.name || "?"}` : "Dang tai..."}
          </span>
          <div style={{ flex: 1 }} />
          {mapeLabel && (
            <span style={{
              fontSize: 11,
              background: "var(--color-background-success)",
              border: "0.5px solid var(--color-border-success)",
              borderRadius: 6, padding: "2px 8px",
              color: "var(--color-text-success)",
            }}>
              {mapeLabel}
            </span>
          )}
          {r2Label && (
            <span style={{
              fontSize: 11,
              background: "var(--color-background-secondary)",
              border: "0.5px solid var(--color-border-tertiary)",
              borderRadius: 6, padding: "2px 8px",
              color: "var(--color-text-info)",
            }}>
              {r2Label}
            </span>
          )}
          <span style={{
            fontSize: 11, padding: "2px 8px", borderRadius: 6, border: "0.5px solid",
            borderColor: health?.status === "ok" ? "var(--color-border-success)" : "var(--color-border-danger)",
            background: health?.status === "ok" ? "var(--color-background-success)" : "var(--color-background-danger)",
            color: health?.status === "ok" ? "var(--color-text-success)" : "var(--color-text-danger)",
          }}>
            {health?.status === "ok" ? "● Connected" : "○ Offline"}
          </span>
        </div>

        {/* Page content */}
        <div style={{ flex: 1, overflow: "hidden", display: "flex" }}>
          {page === "overview"  && <OverviewPage  onSelectFlight={handleSelectFlight} />}
          {page === "optimizer" && <OptimizerPage selectedFlight={selectedFlight} />}
          {page === "simulator" && <SimulatorPage />}
          {page === "routes"    && <RoutesPage />}
          {page === "upload"   && <UploadPage onGoToOverview={() => setPage("overview")} />}
        </div>
      </div>
    </div>
  );
}
