import { defineConfig, loadEnv } from 'vite';
import type { ProxyOptions } from 'vite';
import react from '@vitejs/plugin-react';

// Vite config for hermetic_agent frontend.
// In dev, requests to the path prefix configured in src/config (default `/api`)
// are proxied to the FastAPI-compatible Sanic backend on http://localhost:28000.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = env.VITE_BACKEND_URL || 'http://localhost:28000';
  // Strip any trailing slash so we can safely concatenate paths.
  const target = backendTarget.replace(/\/+$/, '');
  const proxyPrefix = '/api';

  // P8: SSE 长连接 — proxy 不超时, 由 Sanic 后端 (REQUEST_TIMEOUT=600s) 控制
  // 上限. configure(proxy, options) 把后端响应头原样透传, 不让 Vite 注入
  // 默认 keep-alive / close 行为破坏流.
  const streamProxy: ProxyOptions = {
    target,
    changeOrigin: true,
    // /api/agent/chat/stream -> /agent/chat/stream on the backend.
    rewrite: (path) => path.replace(/^\/api/, ''),
    ws: false,
    // 0 = disable Vite 的 socket idle timeout, 让长流 / SSE 不被前端 dev server 切断
    proxyTimeout: 0,
    timeout: 0,
    configure: (proxy) => {
      proxy.on('proxyReq', (_proxyReq, req) => {
        // 关掉 Vite 给 dev 代理加的 Connection: close (Node http 默认行为),
        // 强制 keep-alive, 让后端的 Sanic 维持长连接.
        if (req.socket) {
          req.socket.setKeepAlive(true, 60_000);
        }
      });
    },
  };

  const apiProxy: ProxyOptions = {
    target,
    changeOrigin: true,
    ws: false,
  };

  return {
    plugins: [react()],
    server: {
      port: 23000,
      open: true,
      // 长流 SSE 需要更大的 hmr / file-watch buffer
      hmr: {
        // 防止 Vite HMR overlay 切断 SSE
        overlay: true,
      },
      proxy: {
        [proxyPrefix]: streamProxy,
        '/agent': apiProxy,
        '/ready': apiProxy,
        '/health': apiProxy,
      },
    },
    build: {
      // SSE endpoints emit text/event-stream; make sure dev/prod keep raw streams.
      sourcemap: false,
    },
  };
});
