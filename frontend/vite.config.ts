import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const backendTarget = process.env.VITE_BACKEND_TARGET || 'http://localhost:8080';
const mediaTarget = process.env.VITE_MEDIA_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Wildcard backend (mounted at /wildcards in unified backend)
      // Frontend calls /wildcards/api/* → proxy → backend at /wildcards/*
      '/wildcards': {
        target: backendTarget,
        changeOrigin: true,
        // No rewrite — preserve /wildcards prefix so FastAPI mount works
      },
      // Movie backend (mounted at /movie in unified backend)
      '/movie': {
        target: backendTarget,
        changeOrigin: true,
      },
      // SillyTavern Cards backend (mounted at /cards in unified backend)
      '/cards': {
        target: backendTarget,
        changeOrigin: true,
      },
      // Studio settings / image generation backend
      '/api/studio': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/api/generation': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/api/training': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/api/jobs': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/generated': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/api/suggester': {
        target: backendTarget,
        changeOrigin: true,
      },
      // Media Indexer backend
      '/api/media': {
        target: mediaTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/media/, ''),
      },
    },
  },
});
