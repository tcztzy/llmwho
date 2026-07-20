import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { NDJSONStore } from "./storage.js";
import { summarize } from "./summary.js";

const MODULE_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const HTML_PATHS = [
  join(MODULE_DIRECTORY, "dashboard.html"),
  join(MODULE_DIRECTORY, "..", "..", "python", "src", "llmwho", "dashboard.html"),
];

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
  const store = new NDJSONStore(storagePath);
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
        sendJson(response, 200, summarize(store.read()));
        return;
      }
      if (url.pathname === "/api/events") {
        const requested = Number.parseInt(url.searchParams.get("limit") ?? "500", 10);
        const limit = Number.isFinite(requested) ? Math.min(2000, Math.max(1, requested)) : 500;
        sendJson(response, 200, store.read(limit));
        return;
      }
    } catch {
      sendJson(response, 500, { error: "unable to read local observation store" });
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
