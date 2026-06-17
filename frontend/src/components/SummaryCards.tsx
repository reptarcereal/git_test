import type { Summary } from "../types";

const fmt = (n: number) =>
  n.toLocaleString(undefined, { maximumFractionDigits: 1 });

export function SummaryCards({ summary }: { summary: Summary }) {
  const cards = [
    { label: "Service lines", value: fmt(summary.total_lines), tone: "neutral" },
    { label: "Over cap", value: fmt(summary.lines_over), tone: "over" },
    { label: "Approaching cap", value: fmt(summary.lines_warning), tone: "warning" },
    {
      label: "Total overage",
      value: `${fmt(summary.total_overage_gb)} GB`,
      tone: "over",
    },
    {
      label: "Est. overage cost",
      value: `$${fmt(summary.estimated_overage_cost)}`,
      tone: "over",
    },
  ];
  return (
    <div className="cards">
      {cards.map((c) => (
        <div key={c.label} className={`card card-${c.tone}`}>
          <div className="card-value">{c.value}</div>
          <div className="card-label">{c.label}</div>
        </div>
      ))}
    </div>
  );
}
