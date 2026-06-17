import type { CycleInfo, ServiceLineUsage, Summary } from "./types";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

type LineParams = { status?: string; search?: string; cycle?: string };

function qs(params: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const api = {
  summary: (cycle?: string) => getJSON<Summary>(`/api/summary${qs({ cycle })}`),
  cycles: () => getJSON<CycleInfo[]>("/api/cycles"),
  serviceLines: (params: LineParams = {}) =>
    getJSON<ServiceLineUsage[]>(`/api/service-lines${qs(params)}`),
  refresh: async () => {
    const res = await fetch("/api/refresh", { method: "POST" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  },
  // URL for the CSV export of the currently-filtered table.
  csvUrl: (params: LineParams = {}) => `/api/service-lines.csv${qs(params)}`,
};
