import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Vite config for OpenAgent frontend.
// In dev, requests to the path prefix configured in src/config (default `/api`)
// are proxied to the FastAPI-compatible Sanic backend on http://localhost:8000.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = env.VITE_BACKEND_URL || 'http://localhost:18000';
  // Strip any trailing slash so we can safely concatenate paths.
  const target = backendTarget.replace(/\/+$/, '');
  const proxyPrefix = '/api';

  return {
    plugins: [react()],
    server: {
      port: 3000,
      open: true,
      proxy: {
        // Forward /api/* -> http://localhost:8000/*
        [proxyPrefix]: {
          target,
          changeOrigin: true,
          // /api/agent/chat/stream -> /agent/chat/stream on the backend.
          rewrite: (path) => path.replace(/^\/api/, ''),
          ws: false,
        },
      },
    },
    build: {
      // SSE endpoints emit text/event-stream; make sure dev/prod keep raw streams.
      sourcemap: false,
    },
  };
});
