import { API_BASE_URL, withCuratorAuth } from './config'

/** Attach credentials only to the configured private Flask API origin/path. */
export function analystFetch(url, init = {}) {
  const target = new URL(url, globalThis.location?.href || API_BASE_URL)
  const backend = new URL(API_BASE_URL)
  const options = target.origin === backend.origin && target.pathname.startsWith('/api/')
    ? withCuratorAuth(init)
    : init
  return globalThis.fetch(url, options)
}
