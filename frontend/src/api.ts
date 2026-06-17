import type { ServiceLineUsage, Summary } from "./types";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  summary: () => getJSON<Summary>("/api/summary"),
  serviceLines: (params: { status?: string; search?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.search) q.set("search", params.search);
    const qs = q.toString();
    return getJSON<ServiceLineUsage[]>(`/api/service-lines${qs ? `?${qs}` : ""}`);
  },
  refresh: async () => {
    const res = await fetch("/api/refresh", { method: "POST" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  },
};
