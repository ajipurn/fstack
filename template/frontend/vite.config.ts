import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const API = process.env.API_URL ?? "http://127.0.0.1:8710";

/** Model calls can take minutes; Node's default proxy timeouts would cut them off. */
function longRequests(): Plugin {
  return {
    name: "long-requests",
    configureServer(server) {
      const relax = () => {
        const http = server.httpServer as { timeout: number; requestTimeout: number } | null;
        if (!http) return;
        http.timeout = 0;
        http.requestTimeout = 0;
      };
      relax();
      server.httpServer?.once("listening", relax);
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), longRequests()],
  server: {
    host: "127.0.0.1",
    port: 5710,
    strictPort: true,
    // Unproxied paths fall through to index.html with a 200 — keep every API prefix here.
    proxy: { "/api": { target: API, changeOrigin: false, timeout: 0, proxyTimeout: 0 } },
  },
  preview: { host: "127.0.0.1", port: 5710 },
  // react-dom + Base UI + motion (notch-toast) ≈ 275 KB gzip; pages are split per route.
  build: { chunkSizeWarningLimit: 1000 },
});
