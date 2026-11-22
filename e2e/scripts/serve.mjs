// Lokalny serwer pod testy bez Dockera: świeża baza SQLite z danymi demo (`radar demo`), potem uvicorn.
// Uruchamiany przez `webServer` w playwright.config.ts tylko wtedy, gdy nie ustawiono E2E_BASE_URL.
// Python: RADAR_PYTHON albo app/.venv (Windows/Linux), inaczej `python` z PATH.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");
const app = join(root, "app");
const port = process.env.E2E_PORT || "8010";
const candidates = [process.env.RADAR_PYTHON, join(app, ".venv", "Scripts", "python.exe"), join(app, ".venv", "bin", "python")];
const python = candidates.find(p => p && existsSync(p)) || "python";

const dataDir = join(root, "e2e", ".data");
mkdirSync(dataDir, { recursive: true });
const db = join(dataDir, `e2e-${port}.db`);
rmSync(db, { force: true });  // every run starts from the same seed
const env = {
  ...process.env,
  RADAR_DATABASE_URL: "sqlite:///" + db.replace(/\\/g, "/"),
  RADAR_DEMO_MODE: "1", RADAR_EAGER: "1", RADAR_LLM_PROVIDERS: "mock", RADAR_LOG_LEVEL: "WARNING",
  RADAR_ORG_REGISTRY: join(dataDir, "no-registry.jsonl"),
  PYTHONUTF8: "1",
};

const seed = spawnSync(python, ["-m", "radar.cli", "demo"], { cwd: app, env, stdio: "inherit" });
if (seed.status !== 0) { console.error(`radar demo zakończył się kodem ${seed.status}`); process.exit(seed.status || 1); }

const server = spawn(python, ["-m", "uvicorn", "radar.api.main:app", "--host", "127.0.0.1", "--port", port, "--log-level", "warning"],
  { cwd: app, env, stdio: "inherit" });
const stop = () => server.kill();
process.on("SIGINT", stop); process.on("SIGTERM", stop); process.on("exit", stop);
server.on("exit", code => process.exit(code ?? 0));
