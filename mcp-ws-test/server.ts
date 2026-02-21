import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult, ReadResourceResult } from "@modelcontextprotocol/sdk/types.js";
import fs from "node:fs/promises";
import path from "node:path";
import {
  registerAppTool,
  registerAppResource,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";

const DIST_DIR = path.join(import.meta.dirname, "dist");
const RESOURCE_URI = "ui://hello/mcp-app.html";

const cspMeta = {
  ui: {
    csp: {
      connectDomains: [
        "ws://localhost:9999",
        "http://localhost:9999",
      ],
    },
  },
};

export function createServer(): McpServer {
  const server = new McpServer({
    name: "Hello MCP App",
    version: "0.0.1",
  });

  registerAppTool(
    server,
    "hello",
    {
      title: "Hello",
      description: "Says hello. Displays the greeting in a UI that tests WebSocket connectivity to localhost.",
      inputSchema: {},
      _meta: { ui: { resourceUri: RESOURCE_URI } },
    },
    async (): Promise<CallToolResult> => ({
      content: [{ type: "text", text: `Hello from MCP App! The time is ${new Date().toLocaleTimeString()}` }],
    }),
  );

  registerAppResource(
    server,
    RESOURCE_URI,
    RESOURCE_URI,
    { mimeType: RESOURCE_MIME_TYPE },
    async (): Promise<ReadResourceResult> => {
      const html = await fs.readFile(path.join(DIST_DIR, "mcp-app.html"), "utf-8");
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
