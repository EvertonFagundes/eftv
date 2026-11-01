// vite.config.js - Build config para frontend
import { defineConfig } from 'vite'

export default defineConfig({
  root: '.',
  publicDir: 'public',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: true,
    minify: 'esbuild',
    rollupOptions: {
      input: {
        main: 'public/index.html',
        login: 'public/login.html',
        register: 'public/register.html',
        plans: 'public/plans.html',
        account: 'public/account.html',
        player: 'public/player.html',
      },
    },
  },
  server: {
    port: 3000,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})