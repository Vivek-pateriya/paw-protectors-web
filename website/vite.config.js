import { defineConfig } from "vite";
const proxy = Object.fromEntries(
  [
    "auth",
    "pets",
    "veterinarians",
    "slots",
    "appointments",
    "reminders",
    "admin",
    "health",
  ].map((path) => [
    "/" + path,
    { target: "http://127.0.0.1:8000", changeOrigin: true },
  ]),
);
export default defineConfig({
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 4173, proxy },
  esbuild: { jsx: "automatic" },
});
