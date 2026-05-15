/**
 * Starts a Buckaroo server from the repo root before tests run, tears
 * it down after. We do this in globalSetup rather than Playwright's
 * `webServer` array because launching a non-Node, non-localhost-on-the-
 * config-port background process from there has been flaky for us.
 *
 * Stored handle is read by global-teardown.ts via a temp PID file.
 */
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "..", "..", "..", "..");
const PID_DIR = path.join(tmpdir(), "buckaroo-server-embed-pw");
const PID_FILE = path.join(PID_DIR, "server.pid");

const PORT = 8700;
const HEALTH_URL = `http://127.0.0.1:${PORT}/health`;

async function waitForHealth(timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ok = await new Promise<boolean>((resolve) => {
      const req = http.get(HEALTH_URL, (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      });
      req.on("error", () => resolve(false));
      req.setTimeout(1000, () => {
        req.destroy();
        resolve(false);
      });
    });
    if (ok) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

export default async function globalSetup() {
  mkdirSync(PID_DIR, { recursive: true });

  // If something's already serving /health on this port, reuse it.
  if (await waitForHealth(500)) {
    writeFileSync(PID_FILE, ""); // empty file = nothing to kill
    return;
  }

  const child = spawn(
    "uv",
    ["run", "python", "-m", "buckaroo.server", "--port", String(PORT), "--no-browser"],
    { cwd: REPO_ROOT, detached: true, stdio: "ignore" }
  );
  child.unref();
  writeFileSync(PID_FILE, String(child.pid ?? ""));

  if (!(await waitForHealth(30_000))) {
    throw new Error(
      `Buckaroo server did not become healthy at ${HEALTH_URL} within 30s ` +
        `(pid=${child.pid}). Check that 'uv run python -m buckaroo.server' ` +
        `works from the repo root.`
    );
  }
}
