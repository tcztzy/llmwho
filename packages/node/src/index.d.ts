export type TransportOutcome = "success" | "http_error" | "timeout" | "network_error" | "stream_error";
export interface ObservationV1 {
  schema_version: "1";
  event_id: string;
  timestamp: string;
  source: "passive" | "probe";
  modality: "text" | "image" | "audio" | "embedding" | "multimodal" | "unknown";
  sdk: { name: string; version: string };
  endpoint: { scheme: "http" | "https" | "unknown"; host: string; port?: number; path: string; provider?: string };
  transport: { outcome: TransportOutcome; duration_ms: number; ttft_ms?: number; error_type?: string };
  identity: {
    status: "matched" | "mismatch" | "unknown";
    claimed_model?: string;
    observed_model?: string;
    confidence: number;
    candidates: Array<{ label: string; confidence: number }>;
    evidence: Array<{ kind: string; source: string; value?: string; weight: number }>;
  };
  privacy: { content_captured: false; redactions: number };
  request?: Record<string, unknown>;
  response?: Record<string, unknown>;
  probe?: { case_id: string; passed: boolean; score: number; check?: string };
}

export const VERSION: string;
export interface InitOptions {
  storagePath?: string;
  captureContent?: boolean;
  endpoint?: string | ((url: string) => boolean);
}
export class HookHandle {
  readonly store: NDJSONStore;
  readonly endpoint?: InitOptions["endpoint"];
  readonly captureContent: false;
  active: boolean;
  shutdown(): void;
}
export function init(options?: InitOptions): HookHandle;
export function inferIdentity(claimedModel?: string, declaredModel?: string, responseHeaders?: Record<string, string>): ObservationV1["identity"];
export function newObservation(options: Record<string, unknown>): ObservationV1;
export function validateObservation(event: ObservationV1): void;
export class NDJSONStore {
  constructor(path?: string);
  path: string;
  append(event: ObservationV1): void;
  read(limit?: number): ObservationV1[];
}
export function quantile(values: number[], probability: number): number | null;
export function summarize(events: ObservationV1[]): Record<string, unknown>;
