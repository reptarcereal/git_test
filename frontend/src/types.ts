export type Status = "ok" | "warning" | "over";

export interface ServiceLineUsage {
  service_line_number: string;
  nickname: string | null;
  service_plan: string | null;
  account_number: string | null;
  cycle_start: string | null;
  cycle_end: string | null;
  included_gb: number;
  priority_used_gb: number;
  standard_used_gb: number;
  overage_gb: number;
  used_pct: number;
  status: Status;
  estimated_overage_cost: number;
  captured_at: string | null;
}

export interface Summary {
  total_lines: number;
  lines_ok: number;
  lines_warning: number;
  lines_over: number;
  total_overage_gb: number;
  estimated_overage_cost: number;
  last_updated: string | null;
  mock_mode: boolean;
}
