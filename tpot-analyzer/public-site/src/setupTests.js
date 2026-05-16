import '@testing-library/jest-dom'

// Some test files opt into the 'node' environment (api/* serverless handler
// tests). Skip the browser-only setup when no window exists.
const store = {}
const localStorageMock = {
  getItem: vi.fn((key) => store[key] ?? null),
  setItem: vi.fn((key, value) => { store[key] = String(value) }),
  removeItem: vi.fn((key) => { delete store[key] }),
  clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]) }),
  get length() { return Object.keys(store).length },
  key: vi.fn((i) => Object.keys(store)[i] || null),
}

if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'localStorage', { value: localStorageMock })

  const historyMock = {
    pushState: vi.fn(),
    replaceState: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }
  Object.defineProperty(window, 'history', {
    value: { ...window.history, ...historyMock },
    writable: true,
  })

  window.scrollTo = vi.fn()
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorageMock.clear()
})
