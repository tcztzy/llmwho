import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { JSONLStore } from "./storage.js";
import { summarize } from "./summary.js";

const MODULE_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const HTML_PATHS = [
  join(MODULE_DIRECTORY, "dashboard.html"),
  join(MODULE_DIRECTORY, "..", "..", "python", "src", "llmwho", "dashboard.html"),
];
const COHORT_FILTERS = [
  "endpoint_host",
  "endpoint_path",
  "provider",
  "requested_model",
];
const DAY_MS = 24 * 60 * 60 * 1000;

class QueryError extends Error {}

function canonicalTimestamp(value) {
  if (typeof value !== "string" || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    throw new QueryError("timestamp requires a timezone");
  }
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) throw new QueryError("invalid timestamp");
  return new Date(milliseconds).toISOString();
}

function queryValues(url, allowed) {
  const values = {};
  for (const name of new Set(url.searchParams.keys())) {
    const entries = url.searchParams.getAll(name);
    if (!allowed.has(name) || entries.length !== 1 || !entries[0]) {
      throw new QueryError("invalid query");
    }
    values[name] = entries[0];
  }
  return values;
}

function filters(values, { defaultWindow }) {
  const result = Object.fromEntries(
    COHORT_FILTERS.filter((name) => values[name] !== undefined)
      .map((name) => [name, values[name]]),
  );
  const until = values.until
    ? canonicalTimestamp(values.until)
    : new Date().toISOString();
  const since = values.since
    ? canonicalTimestamp(values.since)
    : (defaultWindow ? new Date(Date.parse(until) - DAY_MS).toISOString() : undefined);
  if (since !== undefined && Date.parse(since) >= Date.parse(until)) {
    throw new QueryError("since must be before until");
  }
  if (since !== undefined) result.since = since;
  if (values.until !== undefined || defaultWindow) result.until = until;
  return result;
}

function matches(event, selected) {
  const timestamp = canonicalTimestamp(event.timestamp);
  return (selected.since === undefined || timestamp >= selected.since)
    && (selected.until === undefined || timestamp < selected.until)
    && (selected.endpoint_host === undefined
      || event.endpoint.host === selected.endpoint_host)
    && (selected.endpoint_path === undefined
      || event.endpoint.path === selected.endpoint_path)
    && (selected.provider === undefined
      || event.endpoint.provider === selected.provider)
    && (selected.requested_model === undefined
      || event.request?.requested_model === selected.requested_model);
}

function summary(store, selected) {
  const value = summarize(store.read().filter((event) => matches(event, selected)));
  value.scope = {
    since: selected.since ?? null,
    until: selected.until ?? null,
    cohort: Object.fromEntries(
      COHORT_FILTERS.filter((name) => selected[name] !== undefined)
        .map((name) => [name, selected[name]]),
    ),
  };
  return value;
}

function encodeCursor(timestamp, eventId) {
  return Buffer.from(JSON.stringify([timestamp, eventId]), "utf8").toString("base64url");
}

function decodeCursor(cursor) {
  try {
    if (!/^[A-Za-z0-9_-]+$/.test(cursor)) throw new Error("invalid encoding");
    const value = JSON.parse(Buffer.from(cursor, "base64url").toString("utf8"));
    if (!Array.isArray(value) || value.length !== 2
        || value.some((item) => typeof item !== "string" || !item)) {
      throw new Error("invalid value");
    }
    return [canonicalTimestamp(value[0]), value[1]];
  } catch {
    throw new QueryError("invalid cursor");
  }
}

function eventPage(store, selected, { limit, cursor }) {
  let rows = store.read()
    .filter((event) => matches(event, selected))
    .map((event) => [canonicalTimestamp(event.timestamp), event.event_id, event])
    .sort(([timestampA, idA], [timestampB, idB]) => (
      timestampA === timestampB ? idB.localeCompare(idA) : timestampB.localeCompare(timestampA)
    ));
  if (cursor) {
    const [timestamp, eventId] = decodeCursor(cursor);
    rows = rows.filter(([rowTimestamp, rowId]) => (
      rowTimestamp < timestamp || (rowTimestamp === timestamp && rowId < eventId)
    ));
  }
  const page = rows.slice(0, limit);
  return {
    events: page.map((row) => row[2]),
    next_cursor: rows.length > limit && page.length
      ? encodeCursor(page.at(-1)[0], page.at(-1)[1])
      : null,
  };
}

async function dashboardHtml() {
  for (const path of HTML_PATHS) {
    try {
      return await readFile(path, "utf8");
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  throw new Error("dashboard asset is missing");
}

function send(response, status, contentType, body) {
  response.writeHead(status, {
    "content-type": contentType,
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "content-security-policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'",
  });
  response.end(body);
}

function sendJson(response, status, value) {
  send(response, status, "application/json; charset=utf-8", JSON.stringify(value));
}

export function createDashboardServer({ storagePath } = {}) {
  const store = new JSONLStore(storagePath);
  return createServer(async (request, response) => {
    const url = new URL(request.url, "http://localhost");
    if (request.method !== "GET") {
      sendJson(response, 405, { error: "method not allowed" });
      return;
    }
    try {
      if (url.pathname === "/") {
        send(response, 200, "text/html; charset=utf-8", await dashboardHtml());
        return;
      }
      if (url.pathname === "/favicon.ico") {
        send(response, 204, "image/x-icon", "");
        return;
      }
      if (url.pathname === "/api/summary") {
        const values = queryValues(
          url,
          new Set(["since", "until", ...COHORT_FILTERS]),
        );
        sendJson(response, 200, summary(store, filters(values, { defaultWindow: true })));
        return;
      }
      if (url.pathname === "/api/events") {
        const values = queryValues(
          url,
          new Set(["since", "until", ...COHORT_FILTERS, "limit", "cursor"]),
        );
        const requested = values.limit === undefined ? 500 : Number(values.limit);
        if (!Number.isInteger(requested) || requested < 1 || requested > 2000) {
          throw new QueryError("invalid limit");
        }
        const cursor = values.cursor;
        delete values.limit;
        delete values.cursor;
        sendJson(response, 200, eventPage(
          store,
          filters(values, { defaultWindow: false }),
          { limit: requested, cursor },
        ));
        return;
      }
    } catch (error) {
      sendJson(
        response,
        error instanceof QueryError ? 400 : 500,
        { error: error instanceof QueryError ? "invalid query" : "unable to read local observation store" },
      );
      return;
    }
    sendJson(response, 404, { error: "not found" });
  });
}

export async function serveDashboard({
  storagePath,
  host = "127.0.0.1",
  port = 7734,
} = {}) {
  if (!Number.isInteger(port) || port < 0 || port > 65535) {
    throw new Error("port must be between 0 and 65535");
  }
  const server = createDashboardServer({ storagePath });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, host, resolve);
  });
  const address = server.address();
  const actualPort = typeof address === "object" ? address.port : port;
  process.stdout.write(`LLMWho dashboard: http://${host}:${actualPort}\n`);
  return server;
}
