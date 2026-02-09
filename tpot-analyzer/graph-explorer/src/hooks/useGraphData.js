/**
 * Custom hook for graph data loading and metrics computation.
 *
 * Handles:
 * - Backend health check on mount
 * - Graph structure loading (nodes + edges)
 * - Metrics computation with concurrency guard
 *
 * @param {Object} options
 * @param {string[]} options.activeSeedList - Current seed handles for metrics
 * @param {boolean} options.includeShadows  - Whether to include shadow nodes
 * @param {Object}  options.weights         - Weight vector { pr, bt, eng }
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchGraphData, checkHealth, computeMetrics } from '../data'

export function useGraphData({ activeSeedList, includeShadows, weights }) {
  const [graphStructure, setGraphStructure] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [computing, setComputing] = useState(false)
  const [backendAvailable, setBackendAvailable] = useState(null)

  const metricsInFlightRef = useRef(false)

  // Check backend health on mount
  useEffect(() => {
    const checkBackend = async () => {
      const isHealthy = await checkHealth()
      setBackendAvailable(isHealthy)
      if (!isHealthy) {
        console.warn('Backend API not available. Some features will be limited.')
      }
    }
    checkBackend()
  }, [])

  // Load graph structure when backend becomes available
  useEffect(() => {
    const loadGraph = async () => {
      if (!backendAvailable) return
      try {
        console.log('[GraphExplorer] Loading graph structure...')
        setLoading(true)
        const structure = await fetchGraphData({
          includeShadow: includeShadows,
          mutualOnly: false,
          minFollowers: 0,
        })
        setGraphStructure(structure)
        console.log('[GraphExplorer] Graph structure loaded - graph can now display!')
      } catch (err) {
        console.error('Failed to load graph structure:', err)
        setError(err)
      } finally {
        setLoading(false)
      }
    }
    loadGraph()
  }, [backendAvailable, includeShadows])

  // Compute metrics when seeds, weights, or structure change
  const recomputeMetrics = useCallback(async () => {
    if (!backendAvailable || !graphStructure) return
    if (metricsInFlightRef.current) {
      console.log('[GraphExplorer] Metrics computation already in progress, skipping...')
      return
    }
    try {
      metricsInFlightRef.current = true
      setComputing(true)
      console.log(`[GraphExplorer] Computing base metrics with ${activeSeedList.length} seeds...`)
      const weightVector = [weights.pr, weights.bt, weights.eng]
      const result = await computeMetrics({
        seeds: activeSeedList,
        weights: weightVector,
        alpha: 0.85,
        resolution: 1.0,
        includeShadow: includeShadows,
        mutualOnly: false,
        minFollowers: 0,
      })
      setMetrics(result)
      console.log('[GraphExplorer] Metrics computed! Tooltips and node sizing updated.')
    } catch (err) {
      console.error('Failed to compute metrics:', err)
      setError(err)
    } finally {
      setComputing(false)
      metricsInFlightRef.current = false
    }
  }, [backendAvailable, graphStructure, activeSeedList, includeShadows, weights])

  useEffect(() => {
    recomputeMetrics()
  }, [recomputeMetrics])

  return {
    graphStructure,
    metrics,
    error,
    loading,
    computing,
    backendAvailable,
    recomputeMetrics,
  }
}
