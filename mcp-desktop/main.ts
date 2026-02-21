import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createServer } from "./server.js";

async function main() {
  await createServer().connect(new StdioServerTransport());
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
