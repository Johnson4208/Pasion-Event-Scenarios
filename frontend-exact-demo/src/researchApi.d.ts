export type Availability = 'READY' | 'UNAVAILABLE' | 'WITHHELD' | 'STALE' | 'ERROR' | 'UNCERTAIN';
export interface ResearchResponse { version: 1; trace_id?: string; contract_version?: string; }
export interface MetricResult {
  value: string | number | null; status: Availability; unit: string;
  currency?: string; source_ids: string[]; known_at: string | null;
  calculation_version: string; reason_codes: string[];
}
export interface FeasibilityResponse extends ResearchResponse {
  status: Availability; quantity: number | null; currency?: string; lot?: number;
  expires_at?: string; reason_codes?: string[];
  riskBudget?: string; maxLoss?: string; potentialProfit?: string;
  positionValue?: string; ratio?: string;
}
export function fetchVersioned<T extends ResearchResponse>(url: string, options?: RequestInit): Promise<T>;
export function feasibilityView(value: FeasibilityResponse | null, clock?: number): Record<string, unknown>;
export function metricText(value: MetricResult | null): string;
export function useCompanyCalculations(ticker: string, period?: string): ResearchResponse | null;
export function bindCompanyIndicators(groups: Array<{name:string;rows:Array<{label:string}>}>, data: unknown): Array<{name:string;rows:Array<Record<string,unknown>>}>;
