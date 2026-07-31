import path from 'node:path'
import react from '@vitejs/plugin-react'
// `vitest/config` re-exports Vite's defineConfig with the `test` block typed.
import { defineConfig } from 'vitest/config'

// `backend` is the Compose service name; override when running Vite on the host
// directly (then the backend is on http://localhost:8000).
const DEV_API_TARGET = process.env.VITE_DEV_PROXY_TARGET ?? 'http://backend:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Inside Docker the file watcher needs polling to see host edits.
    watch: { usePolling: true, interval: 300 },
    strictPort: true,
    // http://localhost:8080 (Caddy) is the intended entrypoint, but hitting the
    // dev server directly is the natural reflex - without these the API calls
    // 404 against Vite itself. Proxying keeps :5173 same-origin too, so the
    // refresh and CSRF cookies behave exactly as they do behind Caddy.
    proxy: {
      '/api': { target: DEV_API_TARGET, changeOrigin: false },
      '/health': { target: DEV_API_TARGET, changeOrigin: false },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // Keep the heavy chart library out of the initial bundle, so the
        // marketing page does not pay for charts it never renders.
        manualChunks(id: string) {
          if (id.includes('node_modules/recharts') || id.includes('node_modules/d3-')) {
            return 'charts'
          }
          // Motion is only used by the marketing page. Splitting it out keeps
          // it a separate parallel download that survives app-code deploys in
          // cache, instead of being welded into the Landing route chunk and
          // re-fetched whenever the copy changes.
          if (id.includes('node_modules/motion') || id.includes('node_modules/framer-motion')) {
            return 'motion'
          }
          if (
            id.includes('node_modules/react-dom') ||
            id.includes('node_modules/react-router') ||
            id.includes('node_modules/react/')
          ) {
            return 'react'
          }
          return undefined
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
