/**
 * Fetch client with retry, timeout, and abort support.
 *
 * Wraps the native fetch API with:
 * - Configurable retry count and exponential backoff
 * - Per-request timeout via AbortController
 * - External AbortSignal propagation (caller can cancel)
 * - Debug logging for each attempt
 */

import { API_TIMEOUT_MS } from './config'

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

export const fetchWithRetry = async (url, options = {}, { retries = 2, backoffMs = 400, timeoutMs = API_TIMEOUT_MS } = {}) => {
  // Extract external signal (e.g., from caller's AbortController)
  const externalSignal = options.signal

  // If already aborted before we start, bail immediately
  if (externalSignal?.aborted) {
    const err = new Error('Aborted')
    err.name = 'AbortError'
    throw err
  }

  let attempt = 0
  let lastError
  const start = performance.now()
  const attemptsMeta = []

  while (attempt <= retries) {
    // Check external abort before each attempt
    if (externalSignal?.aborted) {
      const err = new Error('Aborted')
      err.name = 'AbortError'
      throw err
    }

    const attemptStart = performance.now()
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), timeoutMs)

    // Listen to external signal and propagate abort
    const externalAbortHandler = () => controller.abort()
    externalSignal?.addEventListener('abort', externalAbortHandler)

    try {
      console.debug('[API] fetch start', { url, attempt: attempt + 1, timeoutMs })
      const res = await fetch(url, { ...options, signal: controller.signal })
      clearTimeout(timeout)
      externalSignal?.removeEventListener('abort', externalAbortHandler)
      const dur = Math.round(performance.now() - attemptStart)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} ${res.statusText}`)
      }
      console.debug('[API] fetch ok', { url, attempt: attempt + 1, durationMs: dur, totalMs: Math.round(performance.now() - start) })
      attemptsMeta.push({ attempt: attempt + 1, durationMs: dur, totalMs: Math.round(performance.now() - start), success: true, aborted: false, error: null })
      res._timing = { attempt: attempt + 1, durationMs: dur, totalMs: Math.round(performance.now() - start), attempts: [...attemptsMeta] }
      return res
    } catch (err) {
      clearTimeout(timeout)
      externalSignal?.removeEventListener('abort', externalAbortHandler)
      lastError = err
      const dur = Math.round(performance.now() - attemptStart)
      const total = Math.round(performance.now() - start)
      const wasExternalAbort = externalSignal?.aborted
      attemptsMeta.push({ attempt: attempt + 1, durationMs: dur, totalMs: total, success: false, aborted: err.name === 'AbortError', externalAbort: wasExternalAbort, error: err.message })

      // If externally aborted, don't retry - propagate immediately
      if (wasExternalAbort) {
        console.debug('[API] fetch aborted by caller', { url, attempt: attempt + 1, durationMs: dur, totalMs: total })
        throw err
      }

      if (attempt === retries) {
        console.error('[API] fetch failed (no retries left)', { url, attempt: attempt + 1, durationMs: dur, totalMs: total, error: err.message, aborted: err.name === 'AbortError' })
        break
      }
      const delay = backoffMs * Math.pow(2, attempt)
      console.warn('[API] retrying', { url, attempt: attempt + 1, durationMs: dur, totalMs: total, nextDelayMs: delay, error: err.message, aborted: err.name === 'AbortError' })
      await sleep(delay)
    }
    attempt += 1
  }
  throw lastError
}
