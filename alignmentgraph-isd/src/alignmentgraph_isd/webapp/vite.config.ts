import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Relative asset URLs, so the built app works when FastAPI serves it from
  // its own root as well as from the Vite dev server.
  base: './',
  server: {
    // Not Vite's default 5173: another project holding that port binds IPv4
    // while this one gets IPv6, and since `localhost` resolves to IPv4 first
    // you silently open the wrong app. strictPort makes a clash an error
    // instead of something you discover mid-demo.
    port: Number(process.env.AGISD_UI_PORT) || 5273,
    strictPort: true,
    proxy: {
      // Same-origin in development, which is why the API needs no CORS
      // middleware. No compression here either, or the run event stream would
      // be buffered and arrive all at once at the end.
      '/api': {
        // run-app.sh --dev sets this so its --port is honoured on both sides.
        target: `http://127.0.0.1:${process.env.AGISD_API_PORT || 8000}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
