import { readFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const PID_FILE = path.join(tmpdir(), "buckaroo-server-embed-pw", "server.pid");

export default async function globalTeardown() {
  if (!existsSync(PID_FILE)) return;
  const raw = readFileSync(PID_FILE, "utf8").trim();
  rmSync(PID_FILE, { force: true });
  if (!raw) return; // empty file means we reused an existing server
  const pid = Number(raw);
  if (!Number.isFinite(pid) || pid <= 0) return;
  try {
    process.kill(pid, "SIGTERM");
  } catch {
    // already gone
  }
}
