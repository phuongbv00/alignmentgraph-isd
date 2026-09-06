import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Absolute asset URLs. FastAPI mounts the build at the server root and falls
  // back to index.html for any unknown path, so a relative base broke every URL
  // with a path segment in it: /programs/<id> served the app, and the app then
  // asked for /programs/<id>/assets/*.js, which the same fallback answered with
  // index.html — a blank page and a MIME-type error.
  base: '/',
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
