/**
 * Custom hook for seed list management in the Graph Explorer.
 *
 * Owns:
 * - Graph settings fetch (server-side seed lists + model config)
 * - Seed textarea, custom seeds, preset name state
 * - Available presets and active seed list computation
 * - Persist-to-server and apply-locally seed operations
 *
 * @param {Object} options
 * @param {Function} options.onSettingsLoaded - Called with full settings state on mount
 */

import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { saveSeedList, fetchGraphSettings } from '../data'
import { DEFAULT_PRESETS } from '../config'

const normalizeHandle = (value) => {
  if (!value && value !== 0) return null
  const cleaned = String(value).trim().replace(/^@/, '')
  if (!cleaned) return null
  return cleaned.toLowerCase()
}

const dedupeHandles = (handles = []) => {
  const seen = new Set()
  const result = []
  handles.forEach((handle) => {
    const normalized = normalizeHandle(handle)
    if (normalized && !seen.has(normalized)) {
      seen.add(normalized)
      result.push(normalized)
    }
  })
  return result
}

const toLowerSet = (items = []) => {
  const set = new Set()
  items.forEach((item) => {
    if (!item) return
    set.add(String(item).toLowerCase())
  })
  return set
}

const sanitizeSeedList = (handles = []) => dedupeHandles(handles)

export function useGraphSeeds({ onSettingsLoaded } = {}) {
  const [graphSettings, setGraphSettings] = useState(null)
  const [seedTextarea, setSeedTextarea] = useState('')
  const [customSeeds, setCustomSeeds] = useState([])
  const [presetName, setPresetName] = useState("Adi's Seeds")

  const onSettingsLoadedRef = useRef(onSettingsLoaded)
  useEffect(() => { onSettingsLoadedRef.current = onSettingsLoaded }, [onSettingsLoaded])

  // Fetch graph settings on mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const state = await fetchGraphSettings()
        setGraphSettings(state)
        onSettingsLoadedRef.current?.(state)
      } catch (err) {
        console.error('Failed to load graph settings:', err)
      }
    }
    loadSettings()
  }, [])

  const availablePresets = useMemo(() => {
    const lists = graphSettings?.lists
    if (lists && Object.keys(lists).length > 0) return lists
    return DEFAULT_PRESETS
  }, [graphSettings])

  const activeSeedList = useMemo(() => {
    if (customSeeds.length > 0) return customSeeds
    return availablePresets[presetName] || []
  }, [customSeeds, presetName, availablePresets])

  const customSeedHandleSet = useMemo(() => toLowerSet(customSeeds), [customSeeds])

  // Sync active list from settings when no custom seeds are set
  useEffect(() => {
    if (!graphSettings || customSeeds.length > 0) return
    const active = graphSettings.active_list
    if (!active || !availablePresets[active]) return
    if (presetName !== active) setPresetName(active)
    setSeedTextarea((availablePresets[active] || []).join('\n'))
  }, [graphSettings, availablePresets, customSeeds.length, presetName])

  const determineEditableSeedListName = useCallback(() => {
    const presetNames = new Set(graphSettings?.preset_names || [])
    const userListNames = new Set(graphSettings?.user_list_names || [])
    const existingLists = new Set(Object.keys(graphSettings?.lists || {}))

    let active = graphSettings?.active_list || presetName || 'graph_explorer'
    if (!presetNames.has(active) || userListNames.has(active)) return active

    let candidate = `${active}_custom`
    let counter = 1
    while (existingLists.has(candidate)) {
      candidate = `${active}_custom_${counter++}`
    }
    return candidate
  }, [graphSettings, presetName])

  const applyCustomSeedList = useCallback((nextSeeds, { keepPresetName = false } = {}) => {
    const sanitized = sanitizeSeedList(Array.isArray(nextSeeds) ? nextSeeds : [])
    setCustomSeeds(sanitized)
    setSeedTextarea(sanitized.join('\n'))
    if (!keepPresetName) setPresetName('Custom')
  }, [])

  const persistSeedsToServer = useCallback(async (nextSeeds) => {
    if (!Array.isArray(nextSeeds) || nextSeeds.length === 0) {
      throw new Error('Add at least one account before saving seeds.')
    }
    const sanitized = sanitizeSeedList(nextSeeds)
    if (!sanitized.length) throw new Error('None of the handles were valid.')

    const targetName = determineEditableSeedListName()
    const state = await saveSeedList({
      name: targetName,
      seeds: sanitized,
      setActive: true,
    })
    if (state) {
      setGraphSettings(state)
      setPresetName(state.active_list || targetName)
    }
    return state
  }, [determineEditableSeedListName])

  const handlePresetChange = useCallback((event) => {
    const name = event.target.value
    setPresetName(name)
    if (name === 'Custom') {
      applyCustomSeedList(customSeeds, { keepPresetName: true })
      return
    }
    const presetSeeds = availablePresets[name] || []
    applyCustomSeedList(presetSeeds, { keepPresetName: true })
  }, [customSeeds, availablePresets, applyCustomSeedList])

  const handleApplyCustomSeeds = useCallback(() => {
    const lines = seedTextarea
      .split(/[,\n]/)
      .map((line) => line.trim())
      .filter(Boolean)
    applyCustomSeedList(lines)
  }, [seedTextarea, applyCustomSeedList])

  return {
    // State (exposed for JSX bindings)
    graphSettings,
    seedTextarea,
    setSeedTextarea,
    presetName,
    // Computed
    availablePresets,
    activeSeedList,
    customSeedHandleSet,
    // Handlers
    applyCustomSeedList,
    persistSeedsToServer,
    handlePresetChange,
    handleApplyCustomSeeds,
  }
}
