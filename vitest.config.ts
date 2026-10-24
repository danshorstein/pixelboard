import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts", "shared_ts/**/*.test.ts", "frontend/src/**/*.test.{ts,tsx}"],
    coverage: {
      reporter: ["text", "json-summary"]
    }
  }
});
