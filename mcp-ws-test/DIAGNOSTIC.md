# MCP App Diagnostic — Please Help Debug

## What we're trying to do

We built a minimal MCP App server (the "hello-test" MCP server in your config). It's supposed to render an interactive UI (HTML in an iframe) inside this conversation when its tool is called. Instead, we only see the text result — no iframe/UI appears.

## What we've done so far

1. Created an MCP server using `@modelcontextprotocol/ext-apps` v1.0.x and `@modelcontextprotocol/sdk` v1.24.x
2. Registered a tool called `hello` using `registerAppTool()` with `_meta: { ui: { resourceUri: "ui://hello/mcp-app.html" } }`
3. Registered a UI resource at `ui://hello/mcp-app.html` using `registerAppResource()` that serves a bundled HTML file
4. The HTML uses `import { App } from "@modelcontextprotocol/ext-apps"` and calls `app.connect()`
5. The server runs over stdio transport and responds correctly to `initialize` requests
6. We also added the official `@modelcontextprotocol/server-qr` example to test if any MCP App renders UI

## The server config in claude_desktop_config.json

```json
{
  "mcpServers": {
    "hello-test": {
      "command": "npx",
      "args": ["tsx", "/Users/paddy/buckaroo/mcp-ws-test/main.ts"]
    },
    "qr-code": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-qr", "--stdio"]
    }
  }
}
```

## What we need you to diagnose

1. **Can you see the `hello` tool and/or the `qr-code` tools in your available tools?** List all MCP tools you have access to.

2. **Does this version of Claude Desktop support MCP Apps (interactive UI rendering in iframes)?** Or does it only support standard MCP tools that return text?

3. **When you call the `hello` tool, do you see any indication that it has a UI resource attached (`_meta.ui.resourceUri`)?** Or does it just look like a normal text-returning tool?

4. **Try calling the QR code tool** — ask it to generate a QR code. Does it render a visual QR code UI, or just return text?

5. **Is there anything in the tool metadata that looks wrong or missing?** For reference, a working MCP App tool should have `_meta.ui.resourceUri` pointing to a `ui://` resource.

## What would help

- List every MCP tool you have access to, with their full names
- Tell us if you see any UI/iframe rendering capability in this session
- If MCP Apps aren't supported in this client, tell us what version you are and what would be needed
- If you can see the tools but the UI just isn't rendering, describe what you see when you call them
