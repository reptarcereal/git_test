import type { ServiceLineUsage } from "../types";
import { fmtAZDate } from "../format";

const fmt = (n: number) =>
  n.toLocaleString(undefined, { maximumFractionDigits: 1 });

function UsageBar({ pct, status }: { pct: number; status: string }) {
  return (
    <div className="bar">
      <div
        className={`bar-fill bar-${status}`}
        style={{ width: `${Math.min(pct, 100)}%` }}
      />
      <span className="bar-text">{fmt(pct)}%</span>
    </div>
  );
}

export function ServiceLineTable({ rows }: { rows: ServiceLineUsage[] }) {
  if (rows.length === 0) {
    return <p className="empty">No service lines match the current filter.</p>;
  }
  return (
    <table className="lines">
      <thead>
        <tr>
          <th>Status</th>
          <th>Service line</th>
          <th>Plan</th>
          <th>Used / Included</th>
          <th>Utilization</th>
          <th>Cycle ends</th>
          <th className="num">Overage</th>
          <th className="num">Est. cost</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.service_line_number}>
            <td>
              <span className={`badge badge-${r.status}`}>{r.status}</span>
            </td>
            <td>
              <div className="line-name">{r.nickname ?? r.service_line_number}</div>
              <div className="line-sub">{r.service_line_number}</div>
            </td>
            <td>{r.service_plan ?? "—"}</td>
            <td>
              {fmt(r.priority_used_gb)} / {fmt(r.included_gb)} GB
            </td>
            <td className="bar-cell">
              <UsageBar pct={r.used_pct} status={r.status} />
            </td>
            <td>{r.cycle_end ? fmtAZDate(r.cycle_end) : "—"}</td>
            <td className="num">{r.overage_gb > 0 ? `${fmt(r.overage_gb)} GB` : "—"}</td>
            <td className="num">
              {r.estimated_overage_cost > 0
                ? `$${fmt(r.estimated_overage_cost)}`
                : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
