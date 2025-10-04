#!/usr/bin/env node
import { spawn } from "child_process";
import { fileURLToPath } from "url";
import path from "path";
import fs from "fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const graphExplorerDir = path.resolve(__dirname, "..");
const analyzerRoot = path.resolve(graphExplorerDir, "..");
const outputRelative = path.join("graph-explorer", "public", "analysis_output.json");

const args = process.argv.slice(2);
const options = {
  mutual: true,
  minFollowers: 0,
  preset: "Adi's Seeds",
  seeds: []
};

for (let i = 0; i < args.length; i += 1) {
  const arg = args[i];
  if (arg === "--no-mutual" || arg === "--mutual=false") {
    options.mutual = false;
  } else if (arg === "--mutual") {
    options.mutual = true;
  } else if (arg === "--min-followers" && args[i + 1]) {
    options.minFollowers = Number(args[i + 1]);
    i += 1;
  } else if (arg === "--preset" && args[i + 1]) {
    options.preset = args[i + 1];
    i += 1;
  } else if (arg === "--seeds") {
    const seeds = [];
    let j = i + 1;
    while (j < args.length && !args[j].startsWith("--")) {
      seeds.push(args[j]);
      j += 1;
    }
    options.seeds = seeds;
    i = j - 1;
  }
}

const presetsPath = path.join(analyzerRoot, "docs", "seed_presets.json");
let presetSeeds = [];
if (fs.existsSync(presetsPath)) {
  try {
    const json = JSON.parse(fs.readFileSync(presetsPath, "utf-8"));
    presetSeeds = json?.adi_tpot || [];
    if (options.preset && json[options.preset]) {
      presetSeeds = json[options.preset];
    }
  } catch (err) {
    console.warn("Failed to parse seed_presets.json", err);
  }
}

const seeds = options.seeds.length ? options.seeds : presetSeeds;

const pythonCandidates = [
  process.env.PYTHON,
  process.platform === "win32" ? "py" : "python3",
  "python"
].filter(Boolean);

const runCommand = (cmd) =>
  new Promise((resolve, reject) => {
    const child = spawn(cmd, {
      cwd: analyzerRoot,
      shell: true,
      stdio: "inherit"
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${cmd} exited with ${code}`));
    });
  });

const buildPythonArgs = (python) => {
  const cmdParts = [
    python,
    "-m",
    "scripts.analyze_graph",
    "--output",
    outputRelative
  ];
  if (options.mutual) {
    cmdParts.push("--mutual-only");
  }
  if (options.minFollowers) {
    cmdParts.push("--min-followers", String(options.minFollowers));
  }
  if (seeds.length) {
    cmdParts.push("--seeds", ...seeds);
  }
  return cmdParts.join(" ");
};

const attemptRun = async () => {
  let lastError;
  for (const python of pythonCandidates) {
    if (!python) continue;
    try {
      const cmd = buildPythonArgs(python);
      await runCommand(cmd);
      console.log(`✔ Data refreshed using ${python}`);
      return;
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error("No Python interpreter succeeded");
};

try {
  await attemptRun();
  const publicSeedPath = path.join(graphExplorerDir, "public", "seed_presets.json");
  if (fs.existsSync(presetsPath)) {
    fs.copyFileSync(presetsPath, publicSeedPath);
  }
  console.log(`Analysis written to ${outputRelative}`);
} catch (err) {
  console.error("Failed to refresh data:", err.message || err);
  process.exit(1);
}
