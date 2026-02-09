import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

import { useModelSettings } from './useModelSettings'
import * as discoveryApi from '../discoveryApi'

vi.mock('../discoveryApi', () => ({
  saveModelSettings: vi.fn(),
  fetchAnalysisStatus: vi.fn(),
  runAnalysis: vi.fn(),
}))

vi.mock('../config', () => ({
  DEFAULT_WEIGHTS: { follow: 1, mention: 0.5, reply: 0.3 },
}))

const DEFAULT_MODEL_SETTINGS = {
  alpha: 0.85,
  discovery_weights: { follow: 1, mention: 0.5, reply: 0.3 },
  max_distance: 3,
  limit: 500,
  auto_include_shadow: true,
}

describe('useModelSettings', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    discoveryApi.fetchAnalysisStatus.mockResolvedValue(null)
    discoveryApi.saveModelSettings.mockResolvedValue({
      state: { settings: null },
    })
    discoveryApi.runAnalysis.mockResolvedValue({})
    // Stub window.alert so save-error tests don't throw
    vi.spyOn(window, 'alert').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  // ---------------------------------------------------------------------------
  // Helper: renders the hook and immediately flushes the initial
  // fetchAnalysisStatus call that fires inside useEffect on mount.
  // ---------------------------------------------------------------------------
  async function renderModelSettings(opts) {
    let hookReturn
    await act(async () => {
      hookReturn = renderHook(() => useModelSettings(opts))
      // Flush the initial fetchAnalysisStatus promise.
      await Promise.resolve()
    })
    return hookReturn
  }

  // ---------- 1. Initial state ----------

  describe('initial state', () => {
    it('modelSettings matches DEFAULT_MODEL_SETTINGS', async () => {
      const { result } = await renderModelSettings()
      expect(result.current.modelSettings).toEqual(DEFAULT_MODEL_SETTINGS)
    })

    it('modelSettingsDraft matches DEFAULT_MODEL_SETTINGS', async () => {
      const { result } = await renderModelSettings()
      expect(result.current.modelSettingsDraft).toEqual(DEFAULT_MODEL_SETTINGS)
    })

    it('dirty flag starts as false', async () => {
      const { result } = await renderModelSettings()
      expect(result.current.modelSettingsDirty).toBe(false)
    })

    it('savingModelSettings starts as false', async () => {
      const { result } = await renderModelSettings()
      expect(result.current.savingModelSettings).toBe(false)
    })

    it('analysisPolling starts as false', async () => {
      const { result } = await renderModelSettings()
      expect(result.current.analysisPolling).toBe(false)
    })
  })

  // ---------- 2. Draft handlers set dirty flag ----------

  describe('draft handlers mark dirty flag', () => {
    it('handleAlphaChange marks dirty', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleAlphaChange(0.5)
      })
      expect(result.current.modelSettingsDirty).toBe(true)
    })

    it('handleDiscoveryWeightChange marks dirty', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleDiscoveryWeightChange('follow', 0.9)
      })
      expect(result.current.modelSettingsDirty).toBe(true)
    })

    it('handleModelNumberChange marks dirty', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleModelNumberChange('limit', 100)
      })
      expect(result.current.modelSettingsDirty).toBe(true)
    })

    it('handleToggleAutoShadow marks dirty', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleToggleAutoShadow(false)
      })
      expect(result.current.modelSettingsDirty).toBe(true)
    })
  })

  // ---------- 3. handleAlphaChange ----------

  describe('handleAlphaChange', () => {
    it('updates draft.alpha to the given value', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleAlphaChange(0.42)
      })
      expect(result.current.modelSettingsDraft.alpha).toBe(0.42)
    })

    it('does not change committed modelSettings', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleAlphaChange(0.42)
      })
      expect(result.current.modelSettings.alpha).toBe(0.85)
    })
  })

  // ---------- 4. handleDiscoveryWeightChange ----------

  describe('handleDiscoveryWeightChange', () => {
    it('updates a specific weight key in the draft', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleDiscoveryWeightChange('mention', 0.99)
      })
      expect(result.current.modelSettingsDraft.discovery_weights.mention).toBe(0.99)
    })

    it('preserves other weight keys', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleDiscoveryWeightChange('mention', 0.99)
      })
      expect(result.current.modelSettingsDraft.discovery_weights.follow).toBe(1)
      expect(result.current.modelSettingsDraft.discovery_weights.reply).toBe(0.3)
    })
  })

  // ---------- 5. handleModelNumberChange ----------

  describe('handleModelNumberChange', () => {
    it('updates the max_distance numeric field', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleModelNumberChange('max_distance', 7)
      })
      expect(result.current.modelSettingsDraft.max_distance).toBe(7)
    })

    it('updates the limit numeric field', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleModelNumberChange('limit', 250)
      })
      expect(result.current.modelSettingsDraft.limit).toBe(250)
    })
  })

  // ---------- 6. handleToggleAutoShadow ----------

  describe('handleToggleAutoShadow', () => {
    it('toggles auto_include_shadow to false', async () => {
      const { result } = await renderModelSettings()
      expect(result.current.modelSettingsDraft.auto_include_shadow).toBe(true)
      await act(async () => {
        result.current.handleToggleAutoShadow(false)
      })
      expect(result.current.modelSettingsDraft.auto_include_shadow).toBe(false)
    })

    it('toggles auto_include_shadow back to true', async () => {
      const { result } = await renderModelSettings()
      await act(async () => {
        result.current.handleToggleAutoShadow(false)
      })
      await act(async () => {
        result.current.handleToggleAutoShadow(true)
      })
      expect(result.current.modelSettingsDraft.auto_include_shadow).toBe(true)
    })
  })

  // ---------- 7. handleSaveModelSettings ----------

  describe('handleSaveModelSettings', () => {
    it('calls discoveryApi.saveModelSettings with normalized payload', async () => {
      discoveryApi.saveModelSettings.mockResolvedValue({
        state: { settings: null },
      })

      const { result } = await renderModelSettings()

      // Change the draft so we can verify the normalized payload
      await act(async () => {
        result.current.handleAlphaChange(0.7)
      })

      await act(async () => {
        await result.current.handleSaveModelSettings()
      })

      expect(discoveryApi.saveModelSettings).toHaveBeenCalledTimes(1)
      const payload = discoveryApi.saveModelSettings.mock.calls[0][0]
      expect(payload.alpha).toBe(0.7)
      expect(payload.discovery_weights).toEqual({ follow: 1, mention: 0.5, reply: 0.3 })
      expect(payload.max_distance).toBe(3)
      expect(payload.limit).toBe(500)
      expect(payload.auto_include_shadow).toBe(true)
    })

    it('resets dirty flag after successful save', async () => {
      discoveryApi.saveModelSettings.mockResolvedValue({
        state: { settings: null },
      })
      const { result } = await renderModelSettings()

      await act(async () => {
        result.current.handleAlphaChange(0.7)
      })
      expect(result.current.modelSettingsDirty).toBe(true)

      await act(async () => {
        await result.current.handleSaveModelSettings()
      })
      expect(result.current.modelSettingsDirty).toBe(false)
    })

    it('applies server-returned settings when present in response', async () => {
      const serverSettings = {
        alpha: 0.6,
        discovery_weights: { follow: 0.8, mention: 0.4, reply: 0.2 },
        max_distance: 5,
        limit: 300,
        auto_include_shadow: false,
      }
      discoveryApi.saveModelSettings.mockResolvedValue({
        state: { settings: serverSettings },
      })

      const { result } = await renderModelSettings()

      await act(async () => {
        result.current.handleAlphaChange(0.7)
      })

      await act(async () => {
        await result.current.handleSaveModelSettings()
      })

      // Both committed and draft should reflect the server response
      expect(result.current.modelSettings).toEqual(serverSettings)
      expect(result.current.modelSettingsDraft).toEqual(serverSettings)
    })

    it('falls back to the sent payload when response has no settings', async () => {
      discoveryApi.saveModelSettings.mockResolvedValue({
        state: {},
      })

      const { result } = await renderModelSettings()

      await act(async () => {
        result.current.handleAlphaChange(0.7)
      })

      await act(async () => {
        await result.current.handleSaveModelSettings()
      })

      // Should be the normalized version of the draft
      expect(result.current.modelSettings.alpha).toBe(0.7)
      expect(result.current.modelSettingsDraft.alpha).toBe(0.7)
    })

    it('sets savingModelSettings to true during save, then resets', async () => {
      let resolvePromise
      discoveryApi.saveModelSettings.mockImplementation(
        () => new Promise((resolve) => { resolvePromise = resolve })
      )

      const { result } = await renderModelSettings()

      let savePromise
      act(() => {
        savePromise = result.current.handleSaveModelSettings()
      })

      // While awaiting, savingModelSettings should be true
      expect(result.current.savingModelSettings).toBe(true)

      await act(async () => {
        resolvePromise({ state: {} })
        await savePromise
      })

      expect(result.current.savingModelSettings).toBe(false)
    })

    it('handles save failure gracefully without crashing', async () => {
      discoveryApi.saveModelSettings.mockRejectedValue(new Error('Network down'))
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

      const { result } = await renderModelSettings()

      await act(async () => {
        await result.current.handleSaveModelSettings()
      })

      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to save model settings:',
        expect.any(Error)
      )
      expect(window.alert).toHaveBeenCalledWith('Network down')
      // dirty flag should not be reset on failure
      // (it was not dirty because we didn't change the draft, but savingModelSettings should be reset)
      expect(result.current.savingModelSettings).toBe(false)

      consoleSpy.mockRestore()
    })
  })

  // ---------- 8. applyServerSettings ----------

  describe('applyServerSettings', () => {
    it('overwrites both committed and draft settings', async () => {
      const server = {
        alpha: 0.5,
        discovery_weights: { follow: 0.1, mention: 0.2, reply: 0.3 },
        max_distance: 10,
        limit: 1000,
        auto_include_shadow: false,
      }

      const { result } = await renderModelSettings()

      await act(async () => {
        result.current.applyServerSettings(server)
      })

      expect(result.current.modelSettings.alpha).toBe(0.5)
      expect(result.current.modelSettings.max_distance).toBe(10)
      expect(result.current.modelSettings.limit).toBe(1000)
      expect(result.current.modelSettings.auto_include_shadow).toBe(false)
      expect(result.current.modelSettings.discovery_weights).toEqual({
        follow: 0.1,
        mention: 0.2,
        reply: 0.3,
      })

      // Draft should match committed
      expect(result.current.modelSettingsDraft).toEqual(result.current.modelSettings)
    })

    it('resets dirty flag', async () => {
      const { result } = await renderModelSettings()

      // First make the draft dirty
      await act(async () => {
        result.current.handleAlphaChange(0.1)
      })
      expect(result.current.modelSettingsDirty).toBe(true)

      await act(async () => {
        result.current.applyServerSettings({
          alpha: 0.9,
          discovery_weights: {},
          max_distance: 2,
          limit: 100,
          auto_include_shadow: true,
        })
      })

      expect(result.current.modelSettingsDirty).toBe(false)
    })

    it('merges partial discovery_weights with DEFAULT_WEIGHTS', async () => {
      const { result } = await renderModelSettings()

      await act(async () => {
        result.current.applyServerSettings({
          alpha: 0.8,
          discovery_weights: { follow: 0.77 },
          // no mention or reply
        })
      })

      // follow is overridden, but mention and reply come from DEFAULT_WEIGHTS
      expect(result.current.modelSettings.discovery_weights).toEqual({
        follow: 0.77,
        mention: 0.5,
        reply: 0.3,
      })
    })

    it('uses defaults when server fields are missing', async () => {
      const { result } = await renderModelSettings()

      await act(async () => {
        result.current.applyServerSettings({
          alpha: NaN, // invalid -> falls back to 0.85
          // discovery_weights omitted -> full DEFAULT_WEIGHTS
          // max_distance omitted -> 3
          // limit omitted -> 500
          // auto_include_shadow omitted -> true
        })
      })

      expect(result.current.modelSettings.alpha).toBe(0.85)
      expect(result.current.modelSettings.discovery_weights).toEqual({
        follow: 1,
        mention: 0.5,
        reply: 0.3,
      })
      expect(result.current.modelSettings.max_distance).toBe(3)
      expect(result.current.modelSettings.limit).toBe(500)
      expect(result.current.modelSettings.auto_include_shadow).toBe(true)
    })

    it('does nothing when called with null or undefined', async () => {
      const { result } = await renderModelSettings()

      const before = { ...result.current.modelSettings }
      await act(async () => {
        result.current.applyServerSettings(null)
      })
      expect(result.current.modelSettings).toEqual(before)

      await act(async () => {
        result.current.applyServerSettings(undefined)
      })
      expect(result.current.modelSettings).toEqual(before)
    })
  })

  // ---------- 9. Analysis polling ----------

  describe('analysis polling', () => {
    it('calls fetchAnalysisStatus on mount', async () => {
      await renderModelSettings()
      expect(discoveryApi.fetchAnalysisStatus).toHaveBeenCalledTimes(1)
    })

    it('polls fetchAnalysisStatus every 5 seconds', async () => {
      await renderModelSettings()
      expect(discoveryApi.fetchAnalysisStatus).toHaveBeenCalledTimes(1)

      // Advance 5s -> second call
      await act(async () => {
        vi.advanceTimersByTime(5000)
        await Promise.resolve()
      })
      expect(discoveryApi.fetchAnalysisStatus).toHaveBeenCalledTimes(2)

      // Advance another 5s -> third call
      await act(async () => {
        vi.advanceTimersByTime(5000)
        await Promise.resolve()
      })
      expect(discoveryApi.fetchAnalysisStatus).toHaveBeenCalledTimes(3)
    })

    it('updates analysisStatus with fetched data', async () => {
      const statusData = { status: 'running', progress: 42 }
      discoveryApi.fetchAnalysisStatus.mockResolvedValue(statusData)

      const { result } = await renderModelSettings()

      expect(result.current.analysisStatus).toEqual(statusData)
    })

    it('clears interval on unmount', async () => {
      const { unmount } = await renderModelSettings()

      discoveryApi.fetchAnalysisStatus.mockClear()

      unmount()

      await act(async () => {
        vi.advanceTimersByTime(10000)
      })

      // No calls after unmount
      expect(discoveryApi.fetchAnalysisStatus).not.toHaveBeenCalled()
    })

    it('suppresses errors from fetchAnalysisStatus without crashing', async () => {
      discoveryApi.fetchAnalysisStatus.mockRejectedValue(new Error('timeout'))

      // Should not throw
      const { result } = await renderModelSettings()

      // analysisStatus remains null since the fetch errored
      expect(result.current.analysisStatus).toBe(null)
    })
  })

  // ---------- handleRunAnalysis ----------

  describe('handleRunAnalysis', () => {
    it('calls discoveryApi.runAnalysis and then fetches status', async () => {
      discoveryApi.runAnalysis.mockResolvedValue({})
      discoveryApi.fetchAnalysisStatus.mockResolvedValue({ status: 'complete' })

      const { result } = await renderModelSettings()

      discoveryApi.fetchAnalysisStatus.mockClear()

      await act(async () => {
        await result.current.handleRunAnalysis()
      })

      expect(discoveryApi.runAnalysis).toHaveBeenCalledTimes(1)
      // fetchAnalysisStatus is called once after runAnalysis completes
      expect(discoveryApi.fetchAnalysisStatus).toHaveBeenCalled()
    })

    it('sets analysisPolling during run and resets afterwards', async () => {
      let resolveRun
      discoveryApi.runAnalysis.mockImplementation(
        () => new Promise((resolve) => { resolveRun = resolve })
      )

      const { result } = await renderModelSettings()

      let runPromise
      act(() => {
        runPromise = result.current.handleRunAnalysis()
      })

      expect(result.current.analysisPolling).toBe(true)

      await act(async () => {
        resolveRun({})
        await runPromise
      })

      expect(result.current.analysisPolling).toBe(false)
    })

    it('handles runAnalysis failure gracefully', async () => {
      discoveryApi.runAnalysis.mockRejectedValue(new Error('server error'))
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

      const { result } = await renderModelSettings()

      await act(async () => {
        await result.current.handleRunAnalysis()
      })

      expect(consoleSpy).toHaveBeenCalledWith(
        'Failed to run analysis:',
        expect.any(Error)
      )
      expect(window.alert).toHaveBeenCalledWith('server error')
      expect(result.current.analysisPolling).toBe(false)

      consoleSpy.mockRestore()
    })
  })

  // ---------- 10. onSettingsSaved callback ----------

  describe('onSettingsSaved callback', () => {
    it('fires after a successful save', async () => {
      const onSettingsSaved = vi.fn()
      discoveryApi.saveModelSettings.mockResolvedValue({ state: {} })

      const { result } = await renderModelSettings({ onSettingsSaved })

      await act(async () => {
        await result.current.handleSaveModelSettings()
      })

      expect(onSettingsSaved).toHaveBeenCalledTimes(1)
    })

    it('does not fire when save fails', async () => {
      const onSettingsSaved = vi.fn()
      discoveryApi.saveModelSettings.mockRejectedValue(new Error('fail'))
      vi.spyOn(console, 'error').mockImplementation(() => {})

      const { result } = await renderModelSettings({ onSettingsSaved })

      await act(async () => {
        await result.current.handleSaveModelSettings()
      })

      expect(onSettingsSaved).not.toHaveBeenCalled()
    })

    it('uses the latest callback reference (ref pattern)', async () => {
      const firstCallback = vi.fn()
      const secondCallback = vi.fn()

      discoveryApi.saveModelSettings.mockResolvedValue({ state: {} })

      // Use renderHook with initialProps so rerender can pass new props
      let hookReturn
      await act(async () => {
        hookReturn = renderHook(
          (props) => useModelSettings(props),
          { initialProps: { onSettingsSaved: firstCallback } }
        )
        await Promise.resolve()
      })

      // Update the callback prop (wrap in act to flush the useEffect that syncs the ref)
      await act(async () => {
        hookReturn.rerender({ onSettingsSaved: secondCallback })
      })

      await act(async () => {
        await hookReturn.result.current.handleSaveModelSettings()
      })

      // The ref should have been updated, so only the second fires
      expect(firstCallback).not.toHaveBeenCalled()
      expect(secondCallback).toHaveBeenCalledTimes(1)
    })
  })

  // ---------- normalizeSettingsPayload edge cases ----------

  describe('normalizeSettingsPayload (via save)', () => {
    it('normalizes non-finite max_distance to default 3', async () => {
      discoveryApi.saveModelSettings.mockResolvedValue({ state: {} })

      const { result } = await renderModelSettings()

      await act(async () => {
        result.current.handleModelNumberChange('max_distance', NaN)
      })

      await act(async () => {
        await result.current.handleSaveModelSettings()
      })

      const payload = discoveryApi.saveModelSettings.mock.calls[0][0]
      expect(payload.max_distance).toBe(3)
    })

    it('normalizes non-finite limit to default 500', async () => {
      discoveryApi.saveModelSettings.mockResolvedValue({ state: {} })

      const { result } = await renderModelSettings()

      await act(async () => {
        result.current.handleModelNumberChange('limit', Infinity)
      })

      await act(async () => {
        await result.current.handleSaveModelSettings()
      })

      const payload = discoveryApi.saveModelSettings.mock.calls[0][0]
      expect(payload.limit).toBe(500)
    })

    it('normalizes falsy alpha to default 0.85', async () => {
      discoveryApi.saveModelSettings.mockResolvedValue({ state: {} })

      const { result } = await renderModelSettings()

      await act(async () => {
        result.current.handleAlphaChange(0) // Number(0) || 0.85 => 0.85
      })

      await act(async () => {
        await result.current.handleSaveModelSettings()
      })

      const payload = discoveryApi.saveModelSettings.mock.calls[0][0]
      expect(payload.alpha).toBe(0.85)
    })
  })
})
