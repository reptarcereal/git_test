import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { CycleInfo, ServiceLineUsage, Summary } from "./types";
import { SummaryCards } from "./components/SummaryCards";
import { ServiceLineTable } from "./components/ServiceLineTable";
import { fmtAZDateTime } from "./format";

type Filter = "" | "over" | "warning" | "ok";
const REFRESH_MS = 60_000;

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rows, setRows] = useState<ServiceLineUsage[]>([]);
  const [cycles, setCycles] = useState<CycleInfo[]>([]);
  const [cycle, setCycle] = useState<string>(""); // "" = current/latest
  const [filter, setFilter] = useState<Filter>("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, lines] = await Promise.all([
        api.summary(cycle || undefined),
        api.serviceLines({
          status: filter || undefined,
          search: search || undefined,
          cycle: cycle || undefined,
        }),
      ]);
      setSummary(s);
      setRows(lines);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    }
  }, [filter, search, cycle]);

  useEffect(() => {
    api.cycles().then(setCycles).catch(() => setCycles([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  const triggerRefresh = async () => {
    setLoading(true);
    try {
      await api.refresh();
      api.cycles().then(setCycles).catch(() => {});
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Starlink Overage Dashboard</h1>
          {summary?.last_updated && (
            <p className="muted">
              Updated {fmtAZDateTime(summary.last_updated)} MST
              {summary.mock_mode && <span className="mock-tag">MOCK DATA</span>}
            </p>
          )}
          {summary?.cycle_label && (
            <p className="muted">Billing cycle ending {summary.cycle_label}</p>
          )}
        </div>
        <button onClick={triggerRefresh} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh now"}
        </button>
      </header>

      {error && <div className="error">⚠ {error}</div>}
      {summary && <SummaryCards summary={summary} />}

      <div className="controls">
        <div className="filters">
          {(["", "over", "warning", "ok"] as Filter[]).map((f) => (
            <button
              key={f || "all"}
              className={filter === f ? "active" : ""}
              onClick={() => setFilter(f)}
            >
              {f === "" ? "All" : f}
            </button>
          ))}
        </div>
        <div className="controls-right">
          <select
            className="cycle-select"
            value={cycle}
            onChange={(e) => setCycle(e.target.value)}
            title="Billing cycle"
          >
            <option value="">Current cycle</option>
            {cycles.map((c) => (
              <option key={c.cycle} value={c.cycle}>
                {c.label}
              </option>
            ))}
          </select>
          <input
            type="search"
            placeholder="Search name, customer, or line #"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <a
            className="export-btn"
            href={api.csvUrl({
              status: filter || undefined,
              search: search || undefined,
              cycle: cycle || undefined,
            })}
          >
            Export CSV
          </a>
        </div>
      </div>

      <ServiceLineTable rows={rows} />
    </div>
  );
}
