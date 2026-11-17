import { readFileSync } from "node:fs";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";
import { APP_NAME, monogram } from "./src/app/brand";

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

/**
 * The favicon: the app's initials on its accent, like the logo (src/app/BrandMark.tsx).
 * Drawn from APP_NAME and the accent in tokens.css, so it follows both; inlined into
 * index.html, in dev and in the build.
 */
function favicon(): Plugin {
  return {
    name: "favicon",
    transformIndexHtml() {
      const tokens = readFileSync(new URL("./src/styles/tokens.css", import.meta.url), "utf8");
      const accent = /--accent-base: (#[0-9a-f]{6})/i.exec(tokens)?.[1] ?? "#2f3037";
      const ink = /--accent-ink: (#[0-9a-f]{6}); \/\* fstack:accent-ink/i.exec(tokens)?.[1] ?? "#ffffff";
      const letters = monogram(APP_NAME);
      const size = letters.length > 1 ? 15 : 19;
      const svg =
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">` +
        `<rect width="32" height="32" rx="8" fill="${accent}"/>` +
        `<text x="16" y="16.5" fill="${ink}" font-family="system-ui,-apple-system,Segoe UI,Roboto,sans-serif" ` +
        `font-size="${size}" font-weight="600" letter-spacing="${letters.length > 1 ? -0.4 : 0}" ` +
        `text-anchor="middle" dominant-baseline="central">${letters}</text></svg>`;
      const href = `data:image/svg+xml,${encodeURIComponent(svg)}`;
      return [{ tag: "link", attrs: { rel: "icon", type: "image/svg+xml", href }, injectTo: "head" }];
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), longRequests(), favicon()],
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
