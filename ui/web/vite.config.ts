/// <reference types="vitest/config" />
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 开发时页面由 Vite 端出来，接口转给 `ai4sci serve`（缺省 8765）；打包后由 serve 一并端出，同源不用代理。
// 前缀清单与 server.py 的 API_ROOTS 一致，加端点两边都要登记。
const API_PREFIXES = ['/health', '/cap', '/chats', '/tasks', '/runs', '/flow']

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  server: {
    proxy: Object.fromEntries(
      API_PREFIXES.map((prefix) => [prefix, { target: 'http://127.0.0.1:8765', changeOrigin: false }]),
    ),
  },
  // 单包 200 kB gzip（markdown 渲染 + motion + radix），本地工具可接受；真嫌大再按看板拆包
  build: { chunkSizeWarningLimit: 700 },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
