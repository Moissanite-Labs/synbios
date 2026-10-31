import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: process.env.VITE_BASE || "/",
  build: {
    outDir: process.env.VITE_OUT_DIR || "dist",
  },
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (request) => {
            if (request.getHeader("origin"))
              request.setHeader("origin", "http://127.0.0.1:8765");
          });
        },
      },
    },
  },
});
