import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// 개발 중 /api 요청은 백엔드(uvicorn, 기본 8000번)로 넘긴다 (MVP_SPEC 8.1 VS2 기본값).
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: backend, changeOrigin: true },
    },
  },
})
