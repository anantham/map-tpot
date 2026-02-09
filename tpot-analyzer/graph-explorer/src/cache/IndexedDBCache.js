/**
 * Generic IndexedDB cache with TTL and stale-while-revalidate support.
 *
 * Provides a simple key-value store backed by IndexedDB, with configurable
 * TTL for cache entries. Much larger quota than localStorage (~50MB+ vs 5-10MB).
 *
 * Usage:
 *   const cache = new IndexedDBCache('my-db', 'my-store', { maxAgeMs: 5 * 60 * 1000 })
 *   await cache.set('key1', { some: 'data' })
 *   const result = await cache.get('key1')  // { data, isStale, age }
 */
export class IndexedDBCache {
  constructor(dbName, storeName, { maxAgeMs = 5 * 60 * 1000, label = 'Cache', clearOnSetError = false } = {}) {
    this.dbName = dbName
    this.storeName = storeName
    this.maxAgeMs = maxAgeMs
    this.label = label
    this.clearOnSetError = clearOnSetError
    this.db = null
  }

  async init() {
    if (this.db) return this.db

    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, 1)

      request.onerror = () => reject(request.error)
      request.onsuccess = () => {
        this.db = request.result
        resolve(this.db)
      }

      request.onupgradeneeded = (event) => {
        const db = event.target.result
        if (!db.objectStoreNames.contains(this.storeName)) {
          db.createObjectStore(this.storeName)
        }
      }
    })
  }

  async get(key) {
    try {
      await this.init()

      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction([this.storeName], 'readonly')
        const store = transaction.objectStore(this.storeName)
        const request = store.get(key)

        request.onerror = () => reject(request.error)
        request.onsuccess = () => {
          const cached = request.result
          if (!cached) {
            resolve(null)
            return
          }

          const { data, timestamp } = cached
          const age = Date.now() - timestamp

          resolve({
            data,
            isStale: age > this.maxAgeMs,
            age: Math.floor(age / 1000),
          })
        }
      })
    } catch (error) {
      console.warn(`[${this.label}] Failed to read cache:`, error)
      return null
    }
  }

  async set(key, data) {
    try {
      await this.init()
      const cached = { data, timestamp: Date.now() }

      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction([this.storeName], 'readwrite')
        const store = transaction.objectStore(this.storeName)
        const request = store.put(cached, key)

        request.onerror = () => reject(request.error)
        request.onsuccess = () => {
          console.log(`[${this.label}] Saved to IndexedDB: ${key.substring(0, 80)}`)
          resolve()
        }
      })
    } catch (error) {
      console.warn(`[${this.label}] Failed to write cache:`, error)
      if (this.clearOnSetError) {
        await this.clear()
      }
    }
  }

  async clear() {
    try {
      await this.init()
      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction([this.storeName], 'readwrite')
        const store = transaction.objectStore(this.storeName)
        const request = store.clear()

        request.onerror = () => reject(request.error)
        request.onsuccess = () => {
          console.log(`[${this.label}] Cleared IndexedDB cache`)
          resolve()
        }
      })
    } catch (error) {
      console.warn(`[${this.label}] Failed to clear cache:`, error)
    }
  }
}
