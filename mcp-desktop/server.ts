import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult, ReadResourceResult } from "@modelcontextprotocol/sdk/types.js";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import crypto from "node:crypto";
import { z } from "zod";
import {
  registerAppTool,
  registerAppResource,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";

const SERVER_PORT = Number(process.env.BUCKAROO_PORT ?? 8700);
const SERVER_URL = `http://localhost:${SERVER_PORT}`;
const BUCKAROO_ROOT = path.resolve(import.meta.dirname, "..");
const DIST_DIR = path.join(import.meta.dirname, "dist");
const RESOURCE_URI = "ui://buckaroo/viewer.html";
const SESSION_ID = crypto.randomBytes(6).toString("hex");

const cspMeta = {
  ui: {
    csp: {
      connectDomains: [
        `http://localhost:${SERVER_PORT}`,
        `ws://localhost:${SERVER_PORT}`,
      ],
    },
  },
};

async function healthOk(): Promise<boolean> {
  try {
    const resp = await fetch(`${SERVER_URL}/health`, { signal: AbortSignal.timeout(2000) });
    return resp.ok;
  } catch {
    return false;
  }
}

async function ensureServer(): Promise<void> {
  if (await healthOk()) return;

  const logDir = path.join(process.env.HOME ?? "~", ".buckaroo", "logs");
  await fs.mkdir(logDir, { recursive: true });
  const logFile = path.join(logDir, "server.log");
  const logFh = await fs.open(logFile, "a");

  spawn("uv", ["run", "--directory", BUCKAROO_ROOT, "python", "-m", "buckaroo.server", "--no-browser"], {
    stdio: ["ignore", logFh.fd, logFh.fd],
    detached: true,
  }).unref();

  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 250));
    if (await healthOk()) return;
  }
  throw new Error(`Buckaroo server failed to start within 5s — see ${logFile}`);
}

export function createServer(): McpServer {
  const server = new McpServer(
    { name: "buckaroo-table", version: "0.0.1" },
    {
      instructions:
        "When the user mentions or asks about a CSV, TSV, Parquet, or JSON data file, " +
        "always use the view_data tool to display it interactively in Buckaroo. " +
        "Prefer view_data over reading file contents directly.",
    },
  );

  server.registerPrompt("view", {
    description: "Open a data file in the Buckaroo interactive table viewer",
    argsSchema: {
      path: z.string().describe("Path to the data file"),
    },
  }, async (args) => ({
    messages: [{
      role: "user" as const,
      content: { type: "text" as const, text: `Use the view_data tool to load and display the file at ${args.path}` },
    }],
  }));

  registerAppTool(
    server,
    "view_data",
    {
      title: "Buckaroo Table Viewer",
      description:
        "Load a tabular data file (CSV, TSV, Parquet, JSON) in Buckaroo for interactive viewing.",
      inputSchema: {
        path: z.string().describe("Absolute or relative path to the data file"),
      },
      _meta: { ui: { resourceUri: RESOURCE_URI } },
    },
    async (args: { path: string }): Promise<CallToolResult> => {
      const filePath = path.resolve(args.path);
      await ensureServer();

      const resp = await fetch(`${SERVER_URL}/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: SESSION_ID, path: filePath }),
        signal: AbortSignal.timeout(10000),
      });

      if (!resp.ok) {
        const body = await resp.text();
        throw new Error(`/load failed (${resp.status}): ${body}`);
      }

      const result = (await resp.json()) as { rows: number; columns: { name: string; dtype: string }[] };
      const colLines = result.columns.map((c) => `  - ${c.name} (${c.dtype})`).join("\n");

      const summary = [
        `Loaded **${path.basename(filePath)}** — ${result.rows.toLocaleString()} rows, ${result.columns.length} columns`,
        "",
        `Columns:`,
        colLines,
        "",
        `session:${SESSION_ID}`,
      ].join("\n");

      return { content: [{ type: "text", text: summary }] };
    },
  );

  registerAppResource(
    server,
    RESOURCE_URI,
    RESOURCE_URI,
    { mimeType: RESOURCE_MIME_TYPE },
    async (): Promise<ReadResourceResult> => {
      const html = await fs.readFile(path.join(DIST_DIR, "viewer.html"), "utf-8");
      return {
        contents: [
          {
            uri: RESOURCE_URI,
            mimeType: RESOURCE_MIME_TYPE,
            text: html,
            _meta: cspMeta,
          },
        ],
      };
    },
  );

  return server;
}
