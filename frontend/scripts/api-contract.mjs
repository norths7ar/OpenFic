import { spawnSync } from "node:child_process";
import { cp, mkdir, mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { generate } from "orval";

import config from "../orval.config.ts";

const frontend = fileURLToPath(new URL("..", import.meta.url));
const root = path.dirname(frontend);
const checking = process.argv.includes("--check");
const day = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
})
  .format(new Date())
  .replaceAll("-", "");
const scratchRoot = path.join(root, ".tmp");
await mkdir(scratchRoot, { recursive: true });
const scratch = checking ? await mkdtemp(path.join(scratchRoot, `${day}-api-contract-`)) : null;
const workspace = scratch ? path.join(scratch, "frontend") : frontend;
const generated = path.join(workspace, "src/api/generated");
const schema = path.join(workspace, "openapi.json");
if (scratch) {
  const relative = path.relative(scratchRoot, path.resolve(scratch));
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Scratch directory must be inside the task scratch root.");
  }
}

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit", shell: false });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} failed (${result.status})`);
}

async function tree(directory) {
  const result = new Map();
  async function visit(current) {
    for (const entry of await readdir(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) await visit(full);
      else result.set(path.relative(directory, full), await readFile(full, "utf8"));
    }
  }
  await visit(directory);
  return result;
}

try {
  await mkdir(workspace, { recursive: true });
  if (scratch) {
    await mkdir(path.join(workspace, "src/lib"), { recursive: true });
    await cp(
      path.join(frontend, "src/lib/api-transport.ts"),
      path.join(workspace, "src/lib/api-transport.ts"),
    );
  }
  run(
    "uv",
    [
      "run",
      "--no-sync",
      "python",
      "-B",
      path.join(root, "scripts/export_openapi.py"),
      "--output",
      schema,
    ],
    path.join(root, "backend"),
  );
  const options = config.openfic;
  await generate(
    {
      ...options,
      input: schema,
      output: {
        ...options.output,
        target: path.join(generated, "openfic.ts"),
        schemas: path.join(generated, "models"),
        clean: [generated],
        override: {
          ...options.output.override,
          mutator: { path: path.join(workspace, "src/lib/api-transport.ts"), name: "request" },
        },
      },
    },
    frontend,
  );
  run(
    process.execPath,
    [
      path.join(frontend, "node_modules/oxfmt/bin/oxfmt"),
      "--config",
      path.join(frontend, ".oxfmtrc.json"),
      "--write",
      generated,
      schema,
    ],
    frontend,
  );
  if (checking) {
    const expected = await tree(path.join(frontend, "src/api/generated"));
    const actual = await tree(generated);
    const differences = [...new Set([...expected.keys(), ...actual.keys()])].filter(
      (name) => expected.get(name) !== actual.get(name),
    );
    if (
      (await readFile(schema, "utf8")) !==
      (await readFile(path.join(frontend, "openapi.json"), "utf8"))
    )
      differences.push("openapi.json");
    if (differences.length)
      throw new Error(
        `API contract is out of date. Run pnpm api:generate.\n${differences.join("\n")}`,
      );
    console.log("API contract and generated client are current.");
  }
} finally {
  if (scratch) {
    await rm(scratch, { recursive: true, force: true });
  }
}
