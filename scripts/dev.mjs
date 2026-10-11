import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";

const root = resolve(import.meta.dirname, "..");
const uvicorn = resolve(root, ".venv/bin/uvicorn");
const vite = resolve(root, "node_modules/.bin/vite");

if (!existsSync(uvicorn)) {
  console.error("Python environment missing. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.lock.txt");
  process.exit(1);
}

const children = [
  spawn(uvicorn, ["backend.app:app", "--host", "127.0.0.1", "--port", "8124", "--loop", "asyncio"], {
    cwd: root,
    stdio: "inherit"
  }),
  spawn(vite, ["--config", "frontend/vite.config.ts", "--open", "--host", "127.0.0.1", "--port", "5173"], {
    cwd: root,
    stdio: "inherit"
  })
];

let closing = false;
const stop = (code = 0) => {
  if (closing) return;
  closing = true;
  for (const child of children) {
    if (!child.killed) child.kill("SIGTERM");
  }
  setTimeout(() => process.exit(code), 100).unref();
};

for (const child of children) {
  child.on("error", (error) => {
    console.error(error.message);
    stop(1);
  });
  child.on("exit", (code, signal) => {
    if (!closing && code !== 0) {
      console.error(`Development service stopped (${signal ?? code ?? "unknown"}).`);
      stop(code ?? 1);
    }
  });
}

process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
