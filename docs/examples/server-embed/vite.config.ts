import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /load (HTTP) and /ws/* (WebSocket) to the running Buckaroo
// server so the app can use relative URLs and there's no CORS to deal
// with. Override the target with BUCKAROO_SERVER if you run the server
// somewhere other than http://localhost:8700.
const BUCKAROO_SERVER = process.env.BUCKAROO_SERVER ?? "http://localhost:8700";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/load": { target: BUCKAROO_SERVER, changeOrigin: true },
      "/ws": { target: BUCKAROO_SERVER, ws: true, changeOrigin: true },
    },
  },
});
