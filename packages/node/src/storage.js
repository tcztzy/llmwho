import { appendFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import { validateObservation } from "./observation.js";

export class NDJSONStore {
  constructor(path = join(homedir(), ".llmwho", "events.ndjson")) {
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
}
