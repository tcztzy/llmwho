import { cp, mkdir, rm } from "node:fs/promises";
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
await build({ ...shared, format: "cjs", outfile: "dist/index.cjs" });
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
