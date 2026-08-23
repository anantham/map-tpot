import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
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
