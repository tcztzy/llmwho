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
  collectorUrl?: string;
  collectorToken?: string;
  collectorProtocol?: "native" | "otlp";
}
export class HookHandle {
  readonly store: JSONLStore | RemoteStore;
  readonly endpoint?: InitOptions["endpoint"];
  readonly captureContent: false;
  active: boolean;
  shutdown(): void;
}
export function init(options?: InitOptions): HookHandle;
export interface ProbeOptions {
  baseUrl: string;
  model: string;
  apiKey?: string;
  suite?: "smoke";
  storagePath?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}
export interface ProbeReport {
  schema_version: "1";
  suite: "smoke";
  model: string;
  endpoint: ObservationV1["endpoint"];
  started_at: string;
  completed_at: string;
  completed: boolean;
  capability: { passed: number; total: number; mean_score: number };
  identity: { statuses: Record<string, number>; observed_models: Record<string, number> };
  cases: Array<Record<string, unknown>>;
}
export function probe(options: ProbeOptions): Promise<ProbeReport>;
export function inferIdentity(claimedModel?: string, declaredModel?: string): ObservationV1["identity"];
export function newObservation(options: Record<string, unknown>): ObservationV1;
export function validateObservation(event: ObservationV1): void;
export interface OutputAffinityOptions {
  ngramSize?: number;
  modelWeight?: number;
}
export interface OutputAffinityModel {
  label: string;
  documents: number;
  characters: number;
  ngrams: number;
  entropy_bits: number;
}
export interface OutputAffinityReport {
  metric: "symmetric_smoothed_char_ngram_kl";
  interpretation: "style_divergence";
  unit: "bits_per_character_ngram";
  character_encoding: "utf-16-code-unit";
  ngram_size: number;
  model_weight: number;
  background_weight: number;
  models: OutputAffinityModel[];
  matrix: number[][];
  min_divergence: number;
  max_divergence: number;
}
export interface SciencePluginDescriptor {
  id: string;
  version: string;
  summary: string;
  required_inputs: string[];
  source: string;
}
export interface AnalysisReport<T = Record<string, unknown>> {
  schema_version: "1";
  protocol_version: "1";
  plugin: SciencePluginDescriptor;
  evidence: T;
  limitations: string[];
}
export interface ScienceRuntimeStatus {
  uv_found: boolean;
  uv_path: string;
  uv_version: string | null;
  uv_reason: string | null;
  environment_ready: boolean;
  environment_path: string;
  environment_hash: string;
  engine_version: string;
  engine_source_hash: string;
  python_version: string;
  protocol_version: "1";
  plugin_packages: string[];
}
export interface ScienceRuntimeOptions {
  uvPath?: string;
  cacheDir?: string;
  pythonVersion?: string;
  offline?: boolean;
  pluginPackages?: string[];
  onProgress?: (event: { stream: "stdout" | "stderr"; text: string }) => void;
}
export class ScienceRuntimeError extends Error {
  constructor(code: string, message: string, cause?: unknown);
  readonly code: string;
}
export class ScienceRuntimeManager {
  constructor(options?: ScienceRuntimeOptions);
  status(): Promise<ScienceRuntimeStatus>;
  setup(options?: { offline?: boolean; onProgress?: ScienceRuntimeOptions["onProgress"] }): Promise<ScienceRuntimeStatus>;
  plugins(): Promise<SciencePluginDescriptor[]>;
  run<T = Record<string, unknown>>(
    plugin: string,
    payload: Record<string, unknown>,
  ): Promise<AnalysisReport<T>>;
  outputAffinityMatrix(
    corpora: Record<string, Iterable<string>> | ReadonlyMap<string, Iterable<string>>,
    options?: OutputAffinityOptions,
  ): Promise<AnalysisReport<OutputAffinityReport>>;
  shutdown(): Promise<void>;
}
export const science: ScienceRuntimeManager;
export class JSONLStore {
  constructor(path?: string);
  path: string;
  append(event: ObservationV1): void;
  read(limit?: number): ObservationV1[];
  close(): void;
}
export interface RemoteStoreOptions {
  token?: string;
  protocol?: "native" | "otlp";
  maxQueue?: number;
  batchSize?: number;
  flushIntervalMs?: number;
  requestTimeoutMs?: number;
  fetchImpl?: typeof fetch;
}
export class RemoteStore {
  constructor(url: string, options?: RemoteStoreOptions);
  readonly url: string;
  readonly protocol: "native" | "otlp";
  readonly endpoint: string;
  readonly maxQueue: number;
  readonly batchSize: number;
  closed: boolean;
  dropped: number;
  deliveryFailures: number;
  delivered: number;
  append(event: ObservationV1): boolean;
  flush(): Promise<void>;
  read(limit?: number): Promise<ObservationV1[]>;
  close(options?: { timeoutMs?: number }): Promise<boolean>;
}
export function otlpLogsPayload(events: ObservationV1[]): Record<string, unknown>;
export function quantile(values: number[], probability: number): number | null;
export function summarize(events: ObservationV1[]): Record<string, unknown>;
