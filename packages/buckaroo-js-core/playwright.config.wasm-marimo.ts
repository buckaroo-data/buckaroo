import { defineConfig, devices } from '@playwright/test';
import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';

const PORT = 8765;
const WASM_DIR = path.resolve(__dirname, '../../docs/extra-html/example_notebooks/buckaroo_ddd_tour');

// Simple HTTP server for static WASM HTML files
let server: http.Server | null = null;

export default defineConfig({
  testDir: './pw-tests',
  testMatch: ['wasm-marimo.spec.ts'],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'on-first-retry',
    ...devices['Desktop Chrome'],
  },
  // Longer timeout for WASM: Pyodide initialization can be slow (15-30s)
  timeout: 120_000,

  projects: [
    {
      name: 'chromium-wasm-marimo',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    // Custom startup function instead of command
    async reuseExistingServer() {
      // Check if server is already running
      return new Promise<boolean>(resolve => {
        const testSocket = new (require('net')).Socket();
        testSocket.once('error', () => resolve(false));
        testSocket.once('connect', () => {
          testSocket.destroy();
          resolve(true);
        });
        testSocket.connect(PORT, 'localhost');
      });
    },
    async onExit() {
      if (server) {
        server.close();
      }
    },
  },

  globalSetup: async () => {
    // Start a simple HTTP server
    return new Promise<void>(resolve => {
      const requestHandler = (req: http.IncomingMessage, res: http.ServerResponse) => {
        let filePath = path.join(WASM_DIR, req.url === '/' ? 'index.html' : req.url!);

        // Prevent directory traversal
        const realPath = path.resolve(filePath);
        if (!realPath.startsWith(WASM_DIR)) {
          res.writeHead(403);
          res.end('Forbidden');
          return;
        }

        // Try to read the file
        fs.readFile(filePath, (err, data) => {
          if (err) {
            res.writeHead(404);
            res.end('Not Found');
            return;
          }

          // Set content type
          let contentType = 'text/html';
          if (filePath.endsWith('.js')) contentType = 'application/javascript';
          else if (filePath.endsWith('.css')) contentType = 'text/css';
          else if (filePath.endsWith('.wasm')) contentType = 'application/wasm';
          else if (filePath.endsWith('.json')) contentType = 'application/json';
          else if (filePath.endsWith('.png')) contentType = 'image/png';
          else if (filePath.endsWith('.svg')) contentType = 'image/svg+xml';

          res.writeHead(200, {
            'Content-Type': contentType,
            'Cache-Control': 'no-cache',
            'Access-Control-Allow-Origin': '*',
          });
          res.end(data);
        });
      };

      server = http.createServer(requestHandler);
      server.listen(PORT, 'localhost', () => {
        console.log(`\n✓ WASM HTTP server started on http://localhost:${PORT}`);
        console.log(`  Serving: ${WASM_DIR}\n`);
        resolve();
      });

      server.on('error', (err: any) => {
        if (err.code === 'EADDRINUSE') {
          console.log(`✓ Port ${PORT} already in use, reusing existing server`);
          resolve();
        } else {
          throw err;
        }
      });
    });
  },

  globalTeardown: async () => {
    if (server) {
      server.close();
    }
  },
});
