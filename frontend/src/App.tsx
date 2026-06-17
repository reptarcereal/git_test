import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { ServiceLineUsage, Summary } from "./types";
import { SummaryCards } from "./components/SummaryCards";
import { ServiceLineTable } from "./components/ServiceLineTable";
import { fmtAZDateTime, fmtAZDate } from "./format";

type Filter = "" | "over" | "warning" | "ok";
const REFRESH_MS = 60_000;

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rows, setRows] = useState<ServiceLineUsage[]>([]);
  const [filter, setFilter] = useState<Filter>("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, lines] = await Promise.all([
        api.summary(),
        api.serviceLines({ status: filter || undefined, search: search || undefined }),
      ]);
      setSummary(s);
      setRows(lines);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    }
  }, [filter, search]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  // Billing cycle end is the same across the fleet; surface the current one.
  const cycleEnd = rows.find((r) => r.cycle_end)?.cycle_end ?? null;

  const triggerRefresh = async () => {
    setLoading(true);
    try {
      await api.refresh();
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
          {cycleEnd && (
            <p className="muted">Billing cycle ends {fmtAZDate(cycleEnd)}</p>
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
          <input
            type="search"
            placeholder="Search name or service-line #"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <a
            className="export-btn"
            href={api.csvUrl({ status: filter || undefined, search: search || undefined })}
          >
            Export CSV
          </a>
        </div>
      </div>

      <ServiceLineTable rows={rows} />
    </div>
  );
}
