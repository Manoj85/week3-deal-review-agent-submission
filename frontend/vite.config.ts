import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const proxy = {
  "/api": {
    target: process.env.LOAN_API_TARGET || "http://127.0.0.1:8013",
    rewrite: (path: string) => path.replace(/^\/api/, ""),
    timeout: 900000,
    proxyTimeout: 900000,
  },
};
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
  preview: { host: "127.0.0.1", port: 4173, strictPort: true, proxy },
});
