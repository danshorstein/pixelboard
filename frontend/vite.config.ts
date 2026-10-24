import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const repoRoot = resolve(import.meta.dirname, "..");
const previewUser = process.env.SCOREBOARD_PREVIEW_USER;
const previewPassword = process.env.SCOREBOARD_PREVIEW_PASSWORD;

const previewBasicAuth = () => {
  if (!previewUser || !previewPassword) return undefined;
  const expected = `Basic ${Buffer.from(`${previewUser}:${previewPassword}`).toString("base64")}`;
  return {
    name: "scoreboard-preview-basic-auth",
    configureServer(server: { middlewares: { use: (handler: (request: { headers: Record<string, string | string[] | undefined> }, response: { statusCode: number; setHeader: (name: string, value: string) => void; end: (body: string) => void }, next: () => void) => void) => void } }) {
      server.middlewares.use((request, response, next) => {
        if (request.headers.authorization === expected) return next();
        response.statusCode = 401;
        response.setHeader("WWW-Authenticate", 'Basic realm="Scoreboard preview"');
        response.end("Scoreboard preview authentication required.");
      });
    }
  };
};

export default defineConfig({
  root: import.meta.dirname,
  plugins: [react(), previewBasicAuth()].filter(Boolean),
  server: {
    open: true,
    // Allows ephemeral ngrok preview URLs without opening the dev server to arbitrary hosts.
    allowedHosts: [".ngrok-free.app"],
    proxy: {
      "/api": {
        target: process.env.SCOREBOARD_API_TARGET || "http://127.0.0.1:8124",
        ws: true
      }
    },
    fs: { allow: [repoRoot] }
  },
  build: {
    outDir: resolve(repoRoot, "dist"),
    emptyOutDir: true
  }
});
