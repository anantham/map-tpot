import '@testing-library/jest-dom'

// Mock localStorage for tests
const store = {}
const localStorageMock = {
  getItem: vi.fn((key) => store[key] ?? null),
  setItem: vi.fn((key, value) => { store[key] = String(value) }),
  removeItem: vi.fn((key) => { delete store[key] }),
  clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]) }),
  get length() { return Object.keys(store).length },
  key: vi.fn((i) => Object.keys(store)[i] || null),
}
Object.defineProperty(window, 'localStorage', { value: localStorageMock })

// Mock window.history for routing tests
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

// Mock window.scrollTo
window.scrollTo = vi.fn()

// Reset mocks between tests
beforeEach(() => {
  vi.clearAllMocks()
  localStorageMock.clear()
})
