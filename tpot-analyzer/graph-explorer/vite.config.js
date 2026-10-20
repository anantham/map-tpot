import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        discoveryReview: fileURLToPath(new URL('./discovery-review.html', import.meta.url)),
      },
    },
  },
  server: {
    host: 'localhost',
    port: 5184,
    strictPort: true,
    hmr: {
      host: 'localhost',
      port: 5184,
      protocol: 'ws'
    }
  },
  test: {
    globals: true,
    environment: 'jsdom',
    exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**'],
    setupFiles: './src/setupTests.js',
    deps: {
      optimizer: {
        web: {
          include: ['vitest-canvas-mock']
        }
      }
    }
  }
})
