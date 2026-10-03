import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Куда пересылать запросы к API. По умолчанию FastAPI на локальном порту 8000.
const apiTarget = process.env.API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    // Явный IPv4-адрес: по умолчанию Vite слушает «localhost», который на Windows часто
    // превращается в IPv6 (::1), и обращения по 127.0.0.1 (скрипты, автотесты) не доходят.
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      // Браузер обращается к /api/books на адрес самого фронтенда, а Vite пересылает
      // запрос в FastAPI как /books. Для браузера это «тот же сайт», поэтому CORS не нужен.
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
