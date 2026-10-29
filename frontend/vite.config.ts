/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const api = 'http://localhost:3000';

export default defineConfig({
  plugins: [react()],
  server: {
    // Mesmo layout do nginx (D-14 da 002): /api sem o prefixo, /socket.io e /images direto.
    proxy: {
      '/api': { target: api, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
      '/socket.io': { target: api, ws: true },
      '/images': { target: api },
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    // O teste de contraste lê as variáveis de cor do styles.css.
    css: { include: [/styles\.css/] },
  },
});
