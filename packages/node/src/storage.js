import { appendFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import { validateObservation } from "./observation.js";
import { VERSION } from "./version.js";

export class JSONLStore {
  constructor(path = join(homedir(), ".llmwho", "events.jsonl")) {
    this.path = path;
  }

  append(event) {
    validateObservation(event);
    mkdirSync(dirname(this.path), { recursive: true, mode: 0o700 });
    appendFileSync(this.path, `${JSON.stringify(event)}\n`, { encoding: "utf8", mode: 0o600 });
  }

  read(limit) {
    let text;
    try {
      text = readFileSync(this.path, "utf8");
    } catch (error) {
      if (error.code === "ENOENT") return [];
      throw error;
    }
    const rows = text.split("\n").filter(Boolean).map((line) => JSON.parse(line));
    rows.forEach(validateObservation);
    return limit === undefined ? rows : rows.slice(-limit);
  }

  close() {}
}

const OTLP_EVENT_ATTRIBUTE = "llmwho.event.type";
const OTLP_EVENT_TYPE = "observation";

function collectorBaseUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("collectorUrl must be an HTTP(S) URL without credentials or query");
  }
  if (!["http:", "https:"].includes(parsed.protocol)
      || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("collectorUrl must be an HTTP(S) URL without credentials or query");
  }
  return parsed.href.replace(/\/$/, "");
}

export function otlpLogsPayload(events) {
  return {
    resourceLogs: [
      {
        resource: {
          attributes: [
            { key: "service.name", value: { stringValue: "llmwho-sdk" } },
          ],
        },
        scopeLogs: [
          {
            scope: { name: "llmwho-node", version: VERSION },
            logRecords: events.map((event) => ({
              body: { stringValue: JSON.stringify(event) },
              attributes: [
                {
                  key: OTLP_EVENT_ATTRIBUTE,
                  value: { stringValue: OTLP_EVENT_TYPE },
                },
                {
                  key: "llmwho.schema.version",
                  value: { stringValue: event.schema_version },
                },
              ],
            })),
          },
        ],
      },
    ],
  };
}

export class RemoteStore {
  constructor(url, {
    token,
    protocol = "native",
    maxQueue = 1024,
    batchSize = 50,
    flushIntervalMs = 50,
    requestTimeoutMs = 2000,
    fetchImpl = globalThis.fetch,
  } = {}) {
    if (!["native", "otlp"].includes(protocol)) {
      throw new Error("protocol must be native or otlp");
    }
    if (!Number.isInteger(maxQueue) || maxQueue < 1
        || !Number.isInteger(batchSize) || batchSize < 1) {
      throw new Error("maxQueue and batchSize must be positive integers");
    }
    if (!(flushIntervalMs >= 0) || !(requestTimeoutMs > 0)) {
      throw new Error("invalid remote store timing");
    }
    if (typeof fetchImpl !== "function") {
      throw new Error("RemoteStore requires fetch");
    }
    this.url = collectorBaseUrl(url);
    this.protocol = protocol;
    this.maxQueue = maxQueue;
    this.batchSize = batchSize;
    this.flushIntervalMs = flushIntervalMs;
    this.requestTimeoutMs = requestTimeoutMs;
    this.fetchImpl = fetchImpl;
    this.token = token;
    this.queue = [];
    this.timer = undefined;
    this.inFlight = undefined;
    this.closed = false;
    this.dropped = 0;
    this.deliveryFailures = 0;
    this.delivered = 0;
  }

  get endpoint() {
    return `${this.url}${this.protocol === "otlp" ? "/v1/logs" : "/api/v1/observations"}`;
  }

  append(event) {
    validateObservation(event);
    if (this.closed || this.queue.length >= this.maxQueue) {
      this.dropped += 1;
      return false;
    }
    this.queue.push(event);
    this.#schedule();
    return true;
  }

  #schedule() {
    if (this.timer || this.inFlight || this.closed || !this.queue.length) return;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      void this.#drain();
    }, this.flushIntervalMs);
    this.timer.unref?.();
  }

  #headers() {
    const headers = {
      "content-type": "application/json",
      "user-agent": `llmwho-node/${VERSION}`,
    };
    if (this.token) headers.authorization = `Bearer ${this.token}`;
    return headers;
  }

  #payload(events) {
    return this.protocol === "otlp"
      ? otlpLogsPayload(events)
      : { observations: events };
  }

  async #send(events) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.requestTimeoutMs);
    timeout.unref?.();
    try {
      const response = await this.fetchImpl(this.endpoint, {
        method: "POST",
        headers: this.#headers(),
        body: JSON.stringify(this.#payload(events)),
        signal: controller.signal,
      });
      if (!response?.ok) throw new Error("Collector rejected observations");
      if (typeof response.arrayBuffer === "function") await response.arrayBuffer();
    } finally {
      clearTimeout(timeout);
    }
  }

  async #drain() {
    if (this.inFlight) return this.inFlight;
    const operation = (async () => {
      while (this.queue.length) {
        const batch = this.queue.splice(0, this.batchSize);
        try {
          await this.#send(batch);
          this.delivered += batch.length;
        } catch {
          this.deliveryFailures += batch.length;
        }
      }
    })();
    this.inFlight = operation;
    try {
      await operation;
    } finally {
      this.inFlight = undefined;
      this.#schedule();
    }
  }

  async flush() {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = undefined;
    }
    while (this.queue.length || this.inFlight) {
      if (this.inFlight) await this.inFlight;
      else await this.#drain();
    }
  }

  async read(limit) {
    const suffix = limit === undefined ? "" : `?limit=${Math.max(0, Number(limit) || 0)}`;
    const response = await this.fetchImpl(`${this.url}/api/events${suffix}`, {
      headers: this.#headers(),
    });
    if (!response?.ok) throw new Error("Collector events request failed");
    const events = await response.json();
    if (!Array.isArray(events)) throw new Error("Collector events response must be an array");
    events.forEach(validateObservation);
    return events;
  }

  async close({ timeoutMs = 2000 } = {}) {
    if (this.closed && !this.queue.length && !this.inFlight) return true;
    this.closed = true;
    let timeout;
    const expired = new Promise((resolve) => {
      timeout = setTimeout(() => resolve(false), Math.max(0, timeoutMs));
      timeout.unref?.();
    });
    try {
      return await Promise.race([this.flush().then(() => true), expired]);
    } finally {
      clearTimeout(timeout);
    }
  }
}
