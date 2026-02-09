/**
 * Custom hook for model settings management in the Discovery view.
 *
 * Owns:
 * - Model settings state (committed + draft + dirty flag)
 * - Save-to-server logic with draft normalization
 * - Analysis status polling and rebuild trigger
 * - Draft field handlers (alpha, weights, numbers, toggles)
 *
 * @param {Object}   options
 * @param {Function} options.onSettingsSaved - Called after successful save (e.g. to reset query state)
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { DEFAULT_WEIGHTS } from '../config'
import * as discoveryApi from '../discoveryApi'

const DEFAULT_MODEL_SETTINGS = {
  alpha: 0.85,
  discovery_weights: { ...DEFAULT_WEIGHTS },
  max_distance: 3,
  limit: 500,
  auto_include_shadow: true,
}

const normalizeSettingsPayload = (draft) => ({
  alpha: Number(draft.alpha) || 0.85,
  discovery_weights: { ...draft.discovery_weights },
  max_distance: Number.isFinite(draft.max_distance) ? Number(draft.max_distance) : 3,
  limit: Number.isFinite(draft.limit) ? Number(draft.limit) : 500,
  auto_include_shadow: Boolean(draft.auto_include_shadow),
})

export function useModelSettings({ onSettingsSaved } = {}) {
  const [modelSettings, setModelSettings] = useState(DEFAULT_MODEL_SETTINGS)
  const [modelSettingsDraft, setModelSettingsDraft] = useState(DEFAULT_MODEL_SETTINGS)
  const [modelSettingsDirty, setModelSettingsDirty] = useState(false)
  const [savingModelSettings, setSavingModelSettings] = useState(false)
  const [analysisStatus, setAnalysisStatus] = useState(null)
  const [analysisPolling, setAnalysisPolling] = useState(false)

  const onSettingsSavedRef = useRef(onSettingsSaved)
  useEffect(() => { onSettingsSavedRef.current = onSettingsSaved }, [onSettingsSaved])

  // --- Draft updaters ---

  const updateModelSettingsDraft = useCallback((updater) => {
    setModelSettingsDraft((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      return next
    })
    setModelSettingsDirty(true)
  }, [])

  const handleAlphaChange = useCallback((value) => {
    updateModelSettingsDraft((prev) => ({ ...prev, alpha: value }))
  }, [updateModelSettingsDraft])

  const handleDiscoveryWeightChange = useCallback((key, value) => {
    updateModelSettingsDraft((prev) => ({
      ...prev,
      discovery_weights: { ...prev.discovery_weights, [key]: value },
    }))
  }, [updateModelSettingsDraft])

  const handleModelNumberChange = useCallback((key, value) => {
    updateModelSettingsDraft((prev) => ({ ...prev, [key]: value }))
  }, [updateModelSettingsDraft])

  const handleToggleAutoShadow = useCallback((checked) => {
    updateModelSettingsDraft((prev) => ({ ...prev, auto_include_shadow: checked }))
  }, [updateModelSettingsDraft])

  // --- Save ---

  const handleSaveModelSettings = useCallback(async () => {
    const payload = normalizeSettingsPayload(modelSettingsDraft)
    setSavingModelSettings(true)
    try {
      const data = await discoveryApi.saveModelSettings(payload)
      const updated = data?.state?.settings || payload
      setModelSettings(updated)
      setModelSettingsDraft(updated)
      setModelSettingsDirty(false)
      onSettingsSavedRef.current?.()
    } catch (err) {
      console.error('Failed to save model settings:', err)
      window.alert(err.message || 'Unable to save model settings.')
    } finally {
      setSavingModelSettings(false)
    }
  }, [modelSettingsDraft])

  // --- Analysis polling ---

  const fetchAnalysisStatus = useCallback(async () => {
    try {
      const data = await discoveryApi.fetchAnalysisStatus()
      if (data) setAnalysisStatus(data)
    } catch {
      // Suppress network errors for analysis status
    }
  }, [])

  const handleRunAnalysis = useCallback(async () => {
    setAnalysisPolling(true)
    try {
      await discoveryApi.runAnalysis()
      await fetchAnalysisStatus()
    } catch (err) {
      console.error('Failed to run analysis:', err)
      window.alert(err.message || 'Unable to start analysis.')
    } finally {
      setAnalysisPolling(false)
    }
  }, [fetchAnalysisStatus])

  useEffect(() => {
    fetchAnalysisStatus()
    const interval = setInterval(fetchAnalysisStatus, 5000)
    return () => clearInterval(interval)
  }, [fetchAnalysisStatus])

  // --- External setter for server-loaded settings ---

  const applyServerSettings = useCallback((serverSettings) => {
    if (!serverSettings) return
    const sanitized = {
      alpha: Number(serverSettings.alpha) || 0.85,
      discovery_weights: {
        ...DEFAULT_WEIGHTS,
        ...(serverSettings.discovery_weights || {}),
      },
      max_distance: serverSettings.max_distance ?? 3,
      limit: serverSettings.limit ?? 500,
      auto_include_shadow: serverSettings.auto_include_shadow ?? true,
    }
    setModelSettings(sanitized)
    setModelSettingsDraft(sanitized)
    setModelSettingsDirty(false)
  }, [])

  return {
    // Committed settings (read by query state logic)
    modelSettings,
    // Draft state (bound to form inputs)
    modelSettingsDraft,
    modelSettingsDirty,
    savingModelSettings,
    // Analysis
    analysisStatus,
    analysisPolling,
    // Draft handlers
    handleAlphaChange,
    handleDiscoveryWeightChange,
    handleModelNumberChange,
    handleToggleAutoShadow,
    // Actions
    handleSaveModelSettings,
    handleRunAnalysis,
    // External setter
    applyServerSettings,
  }
}
