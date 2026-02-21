import * as http from 'http';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 8765;
const WASM_DIR = path.resolve(__dirname, '../../docs/extra-html/example_notebooks/buckaroo_ddd_tour');

let server: http.Server | null = null;

async function globalSetup() {
  // Start HTTP server
  return new Promise<void>((resolve, reject) => {
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
          res.end('Not Found: ' + filePath);
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
      console.log(`  Serving WASM directory: ${WASM_DIR}\n`);
      resolve();
    });

    server.on('error', (err: any) => {
      if (err.code === 'EADDRINUSE') {
        // Port already in use - assume previous server is still running
        console.log(`✓ Port ${PORT} already in use (assuming previous server), proceeding...`);
        resolve();
      } else {
        reject(err);
      }
    });
  });
}

export default globalSetup;
