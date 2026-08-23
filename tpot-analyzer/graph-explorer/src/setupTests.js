import '@testing-library/jest-dom'
import 'vitest-canvas-mock'
import { vi } from 'vitest'

class MemoryStorage {
  constructor() {
    this.items = new Map()
  }

  get length() {
    return this.items.size
  }

  clear() {
    this.items.clear()
  }

  getItem(key) {
    const normalized = String(key)
    return this.items.has(normalized) ? this.items.get(normalized) : null
  }

  key(index) {
    return [...this.items.keys()][index] ?? null
  }

  removeItem(key) {
    this.items.delete(String(key))
  }

  setItem(key, value) {
    this.items.set(String(key), String(value))
  }
}

let hasUsableLocalStorage = false
try {
  hasUsableLocalStorage = typeof window.localStorage?.getItem === 'function'
} catch {
  hasUsableLocalStorage = false
}
if (!hasUsableLocalStorage) {
  Object.defineProperty(window, 'Storage', {
    configurable: true,
    value: MemoryStorage,
  })
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: new MemoryStorage(),
  })
}

// Mock ResizeObserver
globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))

// Mock requestAnimationFrame to execute immediately (or just stub it)
// For physics/animations, we often want to control time, but for basic interactions stubbing is usually fine.
globalThis.requestAnimationFrame = (cb) => setTimeout(cb, 0)
globalThis.cancelAnimationFrame = (id) => clearTimeout(id)
