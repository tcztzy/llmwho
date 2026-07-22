import { cp, mkdir, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { build } from "esbuild";

await rm("dist", { recursive: true, force: true });
await mkdir("dist", { recursive: true });

const shared = {
  bundle: true,
  entryPoints: ["src/index.js"],
  platform: "node",
  target: "node18",
  sourcemap: true,
};

await build({ ...shared, format: "esm", outfile: "dist/index.js" });
await build({
  ...shared,
  format: "cjs",
  outfile: "dist/index.cjs",
  plugins: [{
    name: "cjs-runtime-location",
    setup(context) {
      context.onResolve({ filter: /runtime-location\.js$/ }, () => ({
        path: resolve("src/runtime-location-cjs.js"),
      }));
    },
  }],
});
await build({
  bundle: true,
  entryPoints: ["src/cli.js"],
  platform: "node",
  target: "node18",
  format: "esm",
  outfile: "dist/cli.js",
  banner: { js: "#!/usr/bin/env node" },
});
await cp("src/index.d.ts", "dist/index.d.ts");
await cp("../python/src/llmwho/dashboard.html", "dist/dashboard.html");
await mkdir("dist/science-engine", { recursive: true });
await cp("../python/src", "dist/science-engine/src", {
  recursive: true,
  filter: (source) => !source.includes("__pycache__") && !source.endsWith(".pyc"),
});
await cp("../python/pyproject.toml", "dist/science-engine/pyproject.toml");
await cp("../python/uv.lock", "dist/science-engine/uv.lock");
await cp("../python/README.md", "dist/science-engine/README.md");
