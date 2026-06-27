import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("react-markdown") || id.includes("remark-gfm") || id.includes("micromark") || id.includes("unified")) {
            return "vendor-markdown";
          }
          if (id.includes("recharts") || id.includes("d3-") || id.includes("victory-vendor")) {
            return "vendor-charts";
          }
          if (id.includes("lucide-react")) {
            return "vendor-icons";
          }
          if (id.includes("@radix-ui")) {
            return "vendor-radix";
          }
          if (id.includes("react") || id.includes("scheduler")) {
            return "vendor-react";
          }
          return undefined;
        }
      }
    }
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url))
    }
  }
});
