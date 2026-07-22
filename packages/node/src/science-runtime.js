import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import {
  access,
  mkdir,
  open,
  readdir,
  readFile,
  rename,
  stat,
  unlink,
  writeFile,
} from "node:fs/promises";
import { homedir, platform as hostPlatform, arch as hostArch } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";

import { moduleDirectory } from "./runtime-location.js";

const PROTOCOL_VERSION = "1";
const MINIMUM_UV_VERSION = [0, 5, 9];

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function defaultCacheDirectory(environment = process.env) {
  if (environment.LLMWHO_SCIENCE_CACHE) return environment.LLMWHO_SCIENCE_CACHE;
  if (process.platform === "win32") {
    return join(environment.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "llmwho", "science");
  }
  if (process.platform === "darwin") return join(homedir(), "Library", "Caches", "llmwho", "science");
  return join(environment.XDG_CACHE_HOME ?? join(homedir(), ".cache"), "llmwho", "science");
}

function versionTuple(text) {
  const match = String(text).match(/\buv\s+(\d+)\.(\d+)\.(\d+)/u);
  return match ? match.slice(1).map(Number) : null;
}

function versionAtLeast(actual, minimum) {
  for (let index = 0; index < minimum.length; index += 1) {
    if (actual[index] > minimum[index]) return true;
    if (actual[index] < minimum[index]) return false;
  }
  return true;
}

export class ScienceRuntimeError extends Error {
  constructor(code, message, cause) {
    super(message, cause ? { cause } : undefined);
    this.name = "ScienceRuntimeError";
    this.code = code;
  }
}

function safeError(code, message, cause) {
  return new ScienceRuntimeError(code, message, cause);
}

function runCommand(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
      options.onProgress?.({ stream: "stdout", text: chunk });
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
      options.onProgress?.({ stream: "stderr", text: chunk });
    });
    child.once("error", reject);
    child.once("close", (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
        return;
      }
      const error = safeError("COMMAND_FAILED", `${command} exited with status ${code}`);
      error.exitCode = code;
      error.stderr = stderr.slice(-8192);
      reject(error);
    });
  });
}

function serializeCorpora(corpora) {
  const entries = corpora instanceof Map
    ? [...corpora.entries()]
    : corpora && typeof corpora === "object" && !Array.isArray(corpora)
      ? Object.entries(corpora)
      : null;
  if (!entries) throw new TypeError("corpora must be an object or Map");
  return entries.map(([label, documents]) => {
    if (typeof documents === "string" || documents === null || documents === undefined
        || typeof documents[Symbol.iterator] !== "function") {
      return [label, documents];
    }
    return [label, [...documents]];
  });
}

async function exists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function directoryHash(root) {
  const hash = createHash("sha256");
  async function visit(directory, relative = "") {
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      if (entry.name === "__pycache__" || entry.name.endsWith(".pyc")) continue;
      const childRelative = relative ? `${relative}/${entry.name}` : entry.name;
      const child = join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(child, childRelative);
      } else if (entry.isFile()) {
        hash.update(childRelative);
        hash.update("\0");
        hash.update(await readFile(child));
        hash.update("\0");
      }
    }
  }
  await visit(root);
  return hash.digest("hex");
}

async function acquireFileLock(path, operation) {
  const deadline = Date.now() + 60_000;
  let handle;
  while (!handle) {
    try {
      handle = await open(path, "wx");
      await handle.writeFile(JSON.stringify({ pid: process.pid, created_at: Date.now() }));
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      try {
        const details = await stat(path);
        if (Date.now() - details.mtimeMs > 300_000) {
          await unlink(path);
          continue;
        }
      } catch (inspectionError) {
        if (inspectionError.code !== "ENOENT") throw inspectionError;
      }
      if (Date.now() >= deadline) throw safeError("SETUP_LOCK_TIMEOUT", "science setup lock timed out");
      await delay(100);
    }
  }
  try {
    return await operation();
  } finally {
    await handle.close();
    await unlink(path).catch((error) => {
      if (error.code !== "ENOENT") throw error;
    });
  }
}

export class ScienceRuntimeManager {
  constructor(options = {}) {
    this.uvPath = options.uvPath ?? process.env.LLMWHO_UV ?? "uv";
    this.cacheDir = options.cacheDir ?? defaultCacheDirectory();
    this.pythonVersion = options.pythonVersion ?? "3.12";
    if (typeof this.pythonVersion !== "string" || !this.pythonVersion.trim()) {
      throw new TypeError("pythonVersion must be a non-empty string");
    }
    this.offline = options.offline ?? false;
    this.pluginPackages = [...(options.pluginPackages ?? [])];
    if (this.pluginPackages.some((item) => typeof item !== "string" || !item.trim())) {
      throw new TypeError("pluginPackages must contain non-empty package requirements");
    }
    this.engineProjectDir = options.engineProjectDir;
    this.onProgress = options.onProgress;
    this._runCommand = options.commandRunner ?? runCommand;
    this._spawnWorker = options.workerFactory ?? spawn;
    this._worker = null;
    this._pending = new Map();
    this._nextRequestId = 1;
    this._setupPromise = null;
  }

  async _projectDirectory() {
    if (this.engineProjectDir) return this.engineProjectDir;
    const candidates = [
      join(moduleDirectory, "science-engine"),
      join(moduleDirectory, "..", "..", "python"),
    ];
    for (const candidate of candidates) {
      if (await exists(join(candidate, "pyproject.toml"))) return candidate;
    }
    throw safeError("ENGINE_NOT_FOUND", "bundled science engine was not found");
  }

  async _environmentInfo() {
    const projectDir = await this._projectDirectory();
    const [projectText, lockText, sourceHash] = await Promise.all([
      readFile(join(projectDir, "pyproject.toml"), "utf8"),
      readFile(join(projectDir, "uv.lock"), "utf8"),
      directoryHash(join(projectDir, "src")),
    ]);
    const versionMatch = projectText.match(/^version\s*=\s*"([^"]+)"/mu);
    if (!versionMatch) throw safeError("ENGINE_INVALID", "science engine version is missing");
    const engineVersion = versionMatch[1];
    const lockHash = createHash("sha256").update(lockText).digest("hex");
    const identity = {
      engine_version: engineVersion,
      engine_source_hash: sourceHash,
      lock_hash: lockHash,
      python_version: this.pythonVersion,
      plugin_packages: [...this.pluginPackages].sort(),
      platform: hostPlatform(),
      architecture: hostArch(),
    };
    const environmentHash = createHash("sha256")
      .update(JSON.stringify(identity))
      .digest("hex")
      .slice(0, 24);
    const rootDir = join(this.cacheDir, environmentHash);
    const environmentDir = join(rootDir, "environment");
    return {
      ...identity,
      environment_hash: environmentHash,
      project_dir: projectDir,
      root_dir: rootDir,
      environment_dir: environmentDir,
      marker_path: join(rootDir, "ready.json"),
      lock_path: join(this.cacheDir, `${environmentHash}.lock`),
      python_path: process.platform === "win32"
        ? join(environmentDir, "Scripts", "python.exe")
        : join(environmentDir, "bin", "python"),
    };
  }

  async _probeUv() {
    try {
      const result = await this._runCommand(this.uvPath, ["--version"], {
        env: process.env,
      });
      const tuple = versionTuple(result.stdout);
      if (!tuple) return { found: false, path: this.uvPath, version: null, reason: "invalid_version" };
      return {
        found: versionAtLeast(tuple, MINIMUM_UV_VERSION),
        path: this.uvPath,
        version: tuple.join("."),
        reason: versionAtLeast(tuple, MINIMUM_UV_VERSION) ? null : "unsupported_version",
      };
    } catch (error) {
      if (error.code === "ENOENT") {
        return { found: false, path: this.uvPath, version: null, reason: "not_found" };
      }
      return { found: false, path: this.uvPath, version: null, reason: "probe_failed" };
    }
  }

  async _isReady(info) {
    if (!(await exists(info.marker_path)) || !(await exists(info.python_path))) return false;
    try {
      const marker = JSON.parse(await readFile(info.marker_path, "utf8"));
      return marker.environment_hash === info.environment_hash
        && marker.protocol_version === PROTOCOL_VERSION;
    } catch {
      return false;
    }
  }

  async status() {
    const [info, uv] = await Promise.all([this._environmentInfo(), this._probeUv()]);
    return {
      uv_found: uv.found,
      uv_path: uv.path,
      uv_version: uv.version,
      uv_reason: uv.reason,
      environment_ready: await this._isReady(info),
      environment_path: info.environment_dir,
      environment_hash: info.environment_hash,
      engine_version: info.engine_version,
      engine_source_hash: info.engine_source_hash,
      python_version: info.python_version,
      protocol_version: PROTOCOL_VERSION,
      plugin_packages: info.plugin_packages,
    };
  }

  async setup(options = {}) {
    if (this._setupPromise) return this._setupPromise;
    this._setupPromise = this._setup(options);
    try {
      return await this._setupPromise;
    } finally {
      this._setupPromise = null;
    }
  }

  async _setup(options) {
    const info = await this._environmentInfo();
    if (await this._isReady(info)) return this.status();
    const uv = await this._probeUv();
    if (!uv.found) {
      const code = uv.reason === "unsupported_version" ? "UV_UNSUPPORTED" : "UV_NOT_FOUND";
      throw safeError(code, "uv 0.5.9 or newer is required for science analysis");
    }
    await mkdir(this.cacheDir, { recursive: true });
    await acquireFileLock(info.lock_path, async () => {
      if (await this._isReady(info)) return;
      await mkdir(info.root_dir, { recursive: true });
      const offline = options.offline ?? this.offline;
      const environment = {
        ...process.env,
        UV_PROJECT_ENVIRONMENT: info.environment_dir,
        PYTHONNOUSERSITE: "1",
        PYTHONUTF8: "1",
      };
      const syncArgs = [
        "sync",
        "--project",
        info.project_dir,
        "--frozen",
        "--no-dev",
        "--no-editable",
        "--no-install-project",
        "--python",
        info.python_version,
      ];
      if (offline) syncArgs.push("--offline");
      await this._runCommand(this.uvPath, syncArgs, {
        cwd: info.project_dir,
        env: environment,
        onProgress: options.onProgress ?? this.onProgress,
      });
      const engineInstallArgs = ["pip", "install", "--python", info.python_path];
      if (offline) engineInstallArgs.push("--offline");
      engineInstallArgs.push(info.project_dir);
      await this._runCommand(this.uvPath, engineInstallArgs, {
        cwd: info.project_dir,
        env: environment,
        onProgress: options.onProgress ?? this.onProgress,
      });
      if (info.plugin_packages.length > 0) {
        const pluginArgs = ["pip", "install", "--python", info.python_path];
        if (offline) pluginArgs.push("--offline");
        pluginArgs.push(...info.plugin_packages);
        await this._runCommand(this.uvPath, pluginArgs, {
          cwd: info.project_dir,
          env: environment,
          onProgress: options.onProgress ?? this.onProgress,
        });
      }
      await this._runCommand(
        info.python_path,
        ["-c", "from llmwho.science import plugins; plugins()"],
        { cwd: info.project_dir, env: environment },
      );
      const marker = {
        environment_hash: info.environment_hash,
        protocol_version: PROTOCOL_VERSION,
        engine_version: info.engine_version,
        engine_source_hash: info.engine_source_hash,
        python_version: info.python_version,
        plugin_packages: info.plugin_packages,
      };
      const temporaryMarker = `${info.marker_path}.${randomUUID()}.tmp`;
      await writeFile(temporaryMarker, JSON.stringify(marker), "utf8");
      await rename(temporaryMarker, info.marker_path);
    });
    return this.status();
  }

  async _ensureWorker() {
    if (this._worker && this._worker.exitCode === null) return this._worker;
    const info = await this._environmentInfo();
    await this.setup();
    const child = this._spawnWorker(
      info.python_path,
      ["-m", "llmwho.science.worker"],
      {
        cwd: info.project_dir,
        env: {
          ...process.env,
          PYTHONNOUSERSITE: "1",
          PYTHONUTF8: "1",
        },
        shell: false,
        stdio: ["pipe", "pipe", "pipe"],
        windowsHide: true,
      },
    );
    this._worker = child;
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr = `${stderr}${chunk}`.slice(-8192);
    });
    createInterface({ input: child.stdout }).on("line", (line) => this._handleWorkerLine(line));
    child.once("error", (error) => this._failWorker(safeError("WORKER_START_FAILED", "science worker failed to start", error)));
    child.once("exit", (code) => {
      if (this._worker !== child) return;
      const error = safeError("WORKER_EXITED", `science worker exited with status ${code}`);
      error.stderr = stderr;
      this._failWorker(error);
    });
    return child;
  }

  _handleWorkerLine(line) {
    let response;
    try {
      response = JSON.parse(line);
    } catch {
      this._failWorker(safeError("PROTOCOL_ERROR", "science worker emitted invalid JSON"));
      return;
    }
    const pending = this._pending.get(response.id);
    if (!pending) return;
    this._pending.delete(response.id);
    if (response.protocol_version !== PROTOCOL_VERSION) {
      pending.reject(safeError("PROTOCOL_MISMATCH", "science worker protocol mismatch"));
    } else if (response.error) {
      pending.reject(safeError(response.error.code ?? "WORKER_ERROR", "science request failed"));
    } else {
      pending.resolve(response.result);
    }
    if (this._pending.size === 0) this._unrefWorker();
  }

  _failWorker(error) {
    const worker = this._worker;
    this._worker = null;
    for (const pending of this._pending.values()) pending.reject(error);
    this._pending.clear();
    worker?.kill();
  }

  _refWorker() {
    this._worker?.ref?.();
    this._worker?.stdin?.ref?.();
    this._worker?.stdout?.ref?.();
    this._worker?.stderr?.ref?.();
  }

  _unrefWorker() {
    this._worker?.unref?.();
    this._worker?.stdin?.unref?.();
    this._worker?.stdout?.unref?.();
    this._worker?.stderr?.unref?.();
  }

  async _request(method, params = {}) {
    const id = this._nextRequestId;
    this._nextRequestId += 1;
    let request;
    try {
      request = JSON.stringify({
        protocol_version: PROTOCOL_VERSION,
        id,
        method,
        params,
      });
    } catch (error) {
      throw safeError("REQUEST_NOT_SERIALIZABLE", "science request must be JSON-serializable", error);
    }
    const worker = await this._ensureWorker();
    this._refWorker();
    const promise = new Promise((resolve, reject) => {
      this._pending.set(id, { resolve, reject });
    });
    worker.stdin.write(`${request}\n`, (error) => {
      if (!error) return;
      const pending = this._pending.get(id);
      this._pending.delete(id);
      pending?.reject(safeError("WORKER_WRITE_FAILED", "science worker request failed", error));
    });
    return promise;
  }

  async plugins() {
    return this._request("plugins");
  }

  async run(plugin, payload) {
    if (typeof plugin !== "string" || !plugin) throw new TypeError("plugin must be a non-empty string");
    return this._request("analyze", { plugin, payload });
  }

  async outputAffinityMatrix(corpora, options = {}) {
    return this.run("output_affinity", {
      corpora: serializeCorpora(corpora),
      ngram_size: options.ngramSize ?? 3,
      model_weight: options.modelWeight ?? 0.8,
    });
  }

  async shutdown() {
    if (!this._worker) return;
    const worker = this._worker;
    try {
      await this._request("shutdown");
    } catch {
      worker.kill();
    } finally {
      if (this._worker === worker) this._worker = null;
      worker.stdin.end();
    }
  }
}

export const science = new ScienceRuntimeManager();
