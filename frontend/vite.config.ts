import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Docker 에서는 Windows 폴더 변경 감지를 위해 폴링 사용 (docker-compose.yml 의 VITE_POLL)
    watch: process.env.VITE_POLL ? { usePolling: true, interval: 500 } : undefined,
    proxy: {
      "/api": {
        // Docker 에서는 backend 컨테이너로, 그냥 실행할 땐 localhost 로
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
