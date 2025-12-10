import '@testing-library/jest-dom'
import 'vitest-canvas-mock'
import { vi } from 'vitest'

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))

// Mock requestAnimationFrame to execute immediately (or just stub it)
// For physics/animations, we often want to control time, but for basic interactions stubbing is usually fine.
global.requestAnimationFrame = (cb) => setTimeout(cb, 0)
global.cancelAnimationFrame = (id) => clearTimeout(id)
