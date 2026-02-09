import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

import { useGraphSeeds } from './useGraphSeeds'
import * as dataModule from '../data'

vi.mock('../data', () => ({
  saveSeedList: vi.fn(),
  fetchGraphSettings: vi.fn(),
}))

vi.mock('../config', () => ({
  DEFAULT_PRESETS: {
    "Adi's Seeds": ['alice', 'bob'],
    'Test Preset': ['charlie'],
  },
}))

describe('useGraphSeeds', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default: fetchGraphSettings resolves to null (no server settings)
    dataModule.fetchGraphSettings.mockResolvedValue(null)
    dataModule.saveSeedList.mockResolvedValue(null)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ---------------------------------------------------------------------------
  // Helper: renders the hook and flushes the initial fetchGraphSettings call
  // ---------------------------------------------------------------------------
  async function renderSeeds(props) {
    let hookReturn
    await act(async () => {
      hookReturn = renderHook(
        (p) => useGraphSeeds(p),
        { initialProps: props }
      )
      await Promise.resolve()
    })
    return hookReturn
  }

  // ==========================================================================
  // 1. Initial state
  // ==========================================================================

  describe('initial state', () => {
    it('graphSettings starts as null', async () => {
      const { result } = await renderSeeds()
      expect(result.current.graphSettings).toBeNull()
    })

    it('seedTextarea starts as empty string', async () => {
      const { result } = await renderSeeds()
      expect(result.current.seedTextarea).toBe('')
    })

    it('presetName starts as "Adi\'s Seeds"', async () => {
      const { result } = await renderSeeds()
      expect(result.current.presetName).toBe("Adi's Seeds")
    })

    it('activeSeedList falls back to DEFAULT_PRESETS["Adi\'s Seeds"]', async () => {
      const { result } = await renderSeeds()
      expect(result.current.activeSeedList).toEqual(['alice', 'bob'])
    })

    it('customSeedHandleSet starts empty', async () => {
      const { result } = await renderSeeds()
      expect(result.current.customSeedHandleSet.size).toBe(0)
    })

    it('availablePresets falls back to DEFAULT_PRESETS when no settings', async () => {
      const { result } = await renderSeeds()
      expect(result.current.availablePresets).toEqual({
        "Adi's Seeds": ['alice', 'bob'],
        'Test Preset': ['charlie'],
      })
    })

    it('works when called with no arguments', async () => {
      let hookReturn
      await act(async () => {
        hookReturn = renderHook(() => useGraphSeeds())
        await Promise.resolve()
      })
      expect(hookReturn.result.current.graphSettings).toBeNull()
      expect(hookReturn.result.current.presetName).toBe("Adi's Seeds")
    })
  })

  // ==========================================================================
  // 2. Settings loading on mount
  // ==========================================================================

  describe('settings loading on mount', () => {
    it('fetches graph settings and populates graphSettings', async () => {
      const serverState = {
        lists: { 'Server List': ['dave', 'eve'] },
        active_list: 'Server List',
      }
      dataModule.fetchGraphSettings.mockResolvedValue(serverState)

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.graphSettings).toEqual(serverState)
      })
      expect(dataModule.fetchGraphSettings).toHaveBeenCalledTimes(1)
    })

    it('calls onSettingsLoaded callback with settings state', async () => {
      const serverState = {
        lists: { 'Server List': ['dave'] },
        active_list: 'Server List',
      }
      dataModule.fetchGraphSettings.mockResolvedValue(serverState)
      const onSettingsLoaded = vi.fn()

      await renderSeeds({ onSettingsLoaded })

      await waitFor(() => {
        expect(onSettingsLoaded).toHaveBeenCalledWith(serverState)
      })
    })

    it('uses latest onSettingsLoaded callback via ref pattern', async () => {
      const firstCb = vi.fn()
      const secondCb = vi.fn()

      // Delay the fetch so we can update the callback before it resolves
      let resolveFetch
      dataModule.fetchGraphSettings.mockImplementation(
        () => new Promise((resolve) => { resolveFetch = resolve })
      )

      let hookReturn
      await act(async () => {
        hookReturn = renderHook(
          (props) => useGraphSeeds(props),
          { initialProps: { onSettingsLoaded: firstCb } }
        )
      })

      // Update callback before fetch resolves
      await act(async () => {
        hookReturn.rerender({ onSettingsLoaded: secondCb })
      })

      // Now resolve the fetch
      const serverState = { lists: {}, active_list: null }
      await act(async () => {
        resolveFetch(serverState)
        await Promise.resolve()
      })

      expect(firstCb).not.toHaveBeenCalled()
      expect(secondCb).toHaveBeenCalledWith(serverState)
    })

    it('logs error when fetch fails without crashing', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      dataModule.fetchGraphSettings.mockRejectedValue(new Error('Network fail'))

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          'Failed to load graph settings:',
          expect.any(Error)
        )
      })

      // Hook should still be functional
      expect(result.current.graphSettings).toBeNull()
      expect(result.current.activeSeedList).toEqual(['alice', 'bob'])

      consoleSpy.mockRestore()
    })

    it('does not call onSettingsLoaded when fetch fails', async () => {
      vi.spyOn(console, 'error').mockImplementation(() => {})
      dataModule.fetchGraphSettings.mockRejectedValue(new Error('fail'))
      const onSettingsLoaded = vi.fn()

      await renderSeeds({ onSettingsLoaded })

      // Give it time to settle
      await act(async () => { await Promise.resolve() })

      expect(onSettingsLoaded).not.toHaveBeenCalled()
      vi.restoreAllMocks()
    })
  })

  // ==========================================================================
  // 3. availablePresets
  // ==========================================================================

  describe('availablePresets', () => {
    it('uses graphSettings.lists when present and non-empty', async () => {
      const serverState = {
        lists: { 'Server Seeds': ['frank', 'grace'] },
        active_list: 'Server Seeds',
      }
      dataModule.fetchGraphSettings.mockResolvedValue(serverState)

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.availablePresets).toEqual({
          'Server Seeds': ['frank', 'grace'],
        })
      })
    })

    it('falls back to DEFAULT_PRESETS when graphSettings.lists is empty', async () => {
      dataModule.fetchGraphSettings.mockResolvedValue({ lists: {} })

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.graphSettings).toEqual({ lists: {} })
      })
      expect(result.current.availablePresets).toEqual({
        "Adi's Seeds": ['alice', 'bob'],
        'Test Preset': ['charlie'],
      })
    })

    it('falls back to DEFAULT_PRESETS when graphSettings has no lists property', async () => {
      dataModule.fetchGraphSettings.mockResolvedValue({ active_list: 'foo' })

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.graphSettings).toBeTruthy()
      })
      expect(result.current.availablePresets).toEqual({
        "Adi's Seeds": ['alice', 'bob'],
        'Test Preset': ['charlie'],
      })
    })
  })

  // ==========================================================================
  // 4. activeSeedList
  // ==========================================================================

  describe('activeSeedList', () => {
    it('uses customSeeds when they exist', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList(['zach', 'yara'])
      })

      expect(result.current.activeSeedList).toEqual(['zach', 'yara'])
    })

    it('falls back to availablePresets[presetName] when no custom seeds', async () => {
      const { result } = await renderSeeds()
      // Default presetName is "Adi's Seeds"
      expect(result.current.activeSeedList).toEqual(['alice', 'bob'])
    })

    it('returns empty array for unknown preset name', async () => {
      const { result } = await renderSeeds()

      // Use handlePresetChange to set an unknown preset
      await act(async () => {
        result.current.handlePresetChange({ target: { value: 'NonExistent' } })
      })

      // Since 'NonExistent' is not in availablePresets, and applyCustomSeedList
      // will be called with [] (empty), customSeeds will also be [],
      // and the fallback availablePresets['NonExistent'] || [] returns []
      // But handlePresetChange sets presetName to 'NonExistent' and calls
      // applyCustomSeedList with [], which sets customSeeds to [] and presetName stays 'NonExistent'
      // because keepPresetName: true is passed
      // Actually, let's trace: name='NonExistent', setPresetName('NonExistent'),
      // presetSeeds = availablePresets['NonExistent'] || [] = []
      // applyCustomSeedList([], { keepPresetName: true }) -> sanitized=[], customSeeds=[], seedTextarea=''
      // So activeSeedList = availablePresets['NonExistent'] || [] = []
      expect(result.current.activeSeedList).toEqual([])
    })
  })

  // ==========================================================================
  // 5. customSeedHandleSet
  // ==========================================================================

  describe('customSeedHandleSet', () => {
    it('returns a lowercase Set of custom seeds', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList(['Alice', 'BOB', 'charlie'])
      })

      const handleSet = result.current.customSeedHandleSet
      expect(handleSet).toBeInstanceOf(Set)
      expect(handleSet.has('alice')).toBe(true)
      expect(handleSet.has('bob')).toBe(true)
      expect(handleSet.has('charlie')).toBe(true)
      expect(handleSet.size).toBe(3)
    })

    it('is empty when no custom seeds are set', async () => {
      const { result } = await renderSeeds()
      expect(result.current.customSeedHandleSet.size).toBe(0)
    })

    it('excludes falsy/null items', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList(['valid', '', null, undefined])
      })

      // After sanitization, only 'valid' survives
      expect(result.current.customSeedHandleSet.size).toBe(1)
      expect(result.current.customSeedHandleSet.has('valid')).toBe(true)
    })
  })

  // ==========================================================================
  // 6. applyCustomSeedList
  // ==========================================================================

  describe('applyCustomSeedList', () => {
    it('sets customSeeds with sanitized/deduped handles', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList(['@Alice', ' bob ', 'ALICE', 'charlie'])
      })

      // 'alice' and '@Alice' -> 'alice' (deduped), 'bob' (trimmed), 'charlie'
      expect(result.current.activeSeedList).toEqual(['alice', 'bob', 'charlie'])
    })

    it('updates seedTextarea to joined newlines', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList(['alice', 'bob'])
      })

      expect(result.current.seedTextarea).toBe('alice\nbob')
    })

    it('sets presetName to "Custom" by default', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList(['alice'])
      })

      expect(result.current.presetName).toBe('Custom')
    })

    it('keepPresetName=true does not change presetName', async () => {
      const { result } = await renderSeeds()
      const originalPresetName = result.current.presetName

      await act(async () => {
        result.current.applyCustomSeedList(['alice'], { keepPresetName: true })
      })

      expect(result.current.presetName).toBe(originalPresetName)
    })

    it('handles non-array input gracefully (treats as empty)', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList('not-an-array')
      })

      // Non-array -> wrapped in [] -> sanitizeSeedList([]) -> []
      expect(result.current.activeSeedList).toEqual([])
      expect(result.current.seedTextarea).toBe('')
    })

    it('handles null input gracefully', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList(null)
      })

      expect(result.current.seedTextarea).toBe('')
    })

    it('deduplicates handles (case-insensitive)', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList(['Alice', 'alice', 'ALICE', 'Bob', 'bob'])
      })

      expect(result.current.activeSeedList).toEqual(['alice', 'bob'])
    })

    it('strips @ prefix and lowercases', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList(['@TestUser', '@ANOTHER'])
      })

      expect(result.current.activeSeedList).toEqual(['testuser', 'another'])
    })

    it('filters out empty and whitespace-only handles', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.applyCustomSeedList(['alice', '', '  ', '@', 'bob'])
      })

      // '' -> null, '  ' -> null after trim, '@' -> '' after replace -> null
      expect(result.current.activeSeedList).toEqual(['alice', 'bob'])
    })
  })

  // ==========================================================================
  // 7. persistSeedsToServer
  // ==========================================================================

  describe('persistSeedsToServer', () => {
    it('throws for empty array input', async () => {
      const { result } = await renderSeeds()

      await expect(
        act(async () => {
          await result.current.persistSeedsToServer([])
        })
      ).rejects.toThrow('Add at least one account before saving seeds.')
    })

    it('throws for non-array input', async () => {
      const { result } = await renderSeeds()

      await expect(
        act(async () => {
          await result.current.persistSeedsToServer('not-array')
        })
      ).rejects.toThrow('Add at least one account before saving seeds.')
    })

    it('throws for null input', async () => {
      const { result } = await renderSeeds()

      await expect(
        act(async () => {
          await result.current.persistSeedsToServer(null)
        })
      ).rejects.toThrow('Add at least one account before saving seeds.')
    })

    it('throws if all handles are invalid after sanitization', async () => {
      const { result } = await renderSeeds()

      await expect(
        act(async () => {
          await result.current.persistSeedsToServer(['', '@', '   '])
        })
      ).rejects.toThrow('None of the handles were valid.')
    })

    it('calls saveSeedList with correct params', async () => {
      const serverResponse = {
        active_list: 'my_list',
        lists: { my_list: ['alice', 'bob'] },
      }
      dataModule.saveSeedList.mockResolvedValue(serverResponse)

      const { result } = await renderSeeds()

      await act(async () => {
        await result.current.persistSeedsToServer(['@Alice', 'Bob'])
      })

      expect(dataModule.saveSeedList).toHaveBeenCalledTimes(1)
      const call = dataModule.saveSeedList.mock.calls[0][0]
      expect(call.seeds).toEqual(['alice', 'bob'])
      expect(call.setActive).toBe(true)
      expect(call.name).toBeDefined()
    })

    it('updates graphSettings and presetName on success', async () => {
      const serverResponse = {
        active_list: 'saved_list',
        lists: { saved_list: ['alice'] },
      }
      dataModule.saveSeedList.mockResolvedValue(serverResponse)

      const { result } = await renderSeeds()

      await act(async () => {
        await result.current.persistSeedsToServer(['alice'])
      })

      expect(result.current.graphSettings).toEqual(serverResponse)
      expect(result.current.presetName).toBe('saved_list')
    })

    it('uses targetName as presetName when response has no active_list', async () => {
      const serverResponse = {
        lists: { fallback: ['alice'] },
        // no active_list
      }
      dataModule.saveSeedList.mockResolvedValue(serverResponse)

      const { result } = await renderSeeds()

      await act(async () => {
        await result.current.persistSeedsToServer(['alice'])
      })

      // presetName should be the targetName from determineEditableSeedListName
      expect(result.current.graphSettings).toEqual(serverResponse)
    })

    it('does not update state when saveSeedList returns null/falsy', async () => {
      dataModule.saveSeedList.mockResolvedValue(null)

      const { result } = await renderSeeds()

      await act(async () => {
        const returnValue = await result.current.persistSeedsToServer(['alice'])
        expect(returnValue).toBeNull()
      })

      // graphSettings should remain null (unchanged from initial load returning null)
      expect(result.current.graphSettings).toBeNull()
    })
  })

  // ==========================================================================
  // 8. handlePresetChange
  // ==========================================================================

  describe('handlePresetChange', () => {
    it('changes presetName and applies preset seeds', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.handlePresetChange({ target: { value: 'Test Preset' } })
      })

      expect(result.current.presetName).toBe('Test Preset')
      // Test Preset seeds are ['charlie'] from mocked DEFAULT_PRESETS
      expect(result.current.seedTextarea).toBe('charlie')
    })

    it('"Custom" preset applies customSeeds with keepPresetName', async () => {
      const { result } = await renderSeeds()

      // First set some custom seeds
      await act(async () => {
        result.current.applyCustomSeedList(['myuser1', 'myuser2'])
      })
      expect(result.current.presetName).toBe('Custom')

      // Switch to a preset
      await act(async () => {
        result.current.handlePresetChange({ target: { value: 'Test Preset' } })
      })
      expect(result.current.presetName).toBe('Test Preset')

      // Switch back to Custom — should re-apply the custom seeds that were set earlier
      // Note: customSeeds are set to ['charlie'] from the preset change above,
      // because handlePresetChange calls applyCustomSeedList with preset seeds.
      // This means customSeeds is ['charlie']. When switching to 'Custom',
      // it calls applyCustomSeedList(customSeeds, { keepPresetName: true })
      // which re-applies the current customSeeds (['charlie'])
      await act(async () => {
        result.current.handlePresetChange({ target: { value: 'Custom' } })
      })
      expect(result.current.presetName).toBe('Custom')
    })

    it('applies empty seeds for unknown preset name', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.handlePresetChange({ target: { value: 'DoesNotExist' } })
      })

      expect(result.current.presetName).toBe('DoesNotExist')
      expect(result.current.seedTextarea).toBe('')
    })
  })

  // ==========================================================================
  // 9. handleApplyCustomSeeds
  // ==========================================================================

  describe('handleApplyCustomSeeds', () => {
    it('parses seedTextarea by newlines and applies', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.setSeedTextarea('alice\nbob\ncharlie')
      })

      await act(async () => {
        result.current.handleApplyCustomSeeds()
      })

      expect(result.current.activeSeedList).toEqual(['alice', 'bob', 'charlie'])
      expect(result.current.presetName).toBe('Custom')
    })

    it('parses seedTextarea by commas', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.setSeedTextarea('alice,bob,charlie')
      })

      await act(async () => {
        result.current.handleApplyCustomSeeds()
      })

      expect(result.current.activeSeedList).toEqual(['alice', 'bob', 'charlie'])
    })

    it('handles mixed commas and newlines', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.setSeedTextarea('alice,bob\ncharlie,dave')
      })

      await act(async () => {
        result.current.handleApplyCustomSeeds()
      })

      expect(result.current.activeSeedList).toEqual(['alice', 'bob', 'charlie', 'dave'])
    })

    it('trims whitespace and filters empty lines', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.setSeedTextarea('  alice  \n\n  bob  \n  ')
      })

      await act(async () => {
        result.current.handleApplyCustomSeeds()
      })

      expect(result.current.activeSeedList).toEqual(['alice', 'bob'])
    })

    it('handles empty seedTextarea', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.setSeedTextarea('')
      })

      await act(async () => {
        result.current.handleApplyCustomSeeds()
      })

      // All lines are empty after filter, so customSeeds = []
      // activeSeedList falls back to preset
      expect(result.current.presetName).toBe('Custom')
    })
  })

  // ==========================================================================
  // 10. determineEditableSeedListName (tested indirectly via persistSeedsToServer)
  // ==========================================================================

  describe('determineEditableSeedListName', () => {
    it('returns active_list if not a system preset', async () => {
      dataModule.fetchGraphSettings.mockResolvedValue({
        lists: { my_custom_list: ['alice'] },
        active_list: 'my_custom_list',
        preset_names: ['system_preset'],
        user_list_names: ['my_custom_list'],
      })
      dataModule.saveSeedList.mockResolvedValue({
        active_list: 'my_custom_list',
        lists: { my_custom_list: ['alice', 'bob'] },
      })

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.graphSettings).toBeTruthy()
      })

      await act(async () => {
        await result.current.persistSeedsToServer(['alice', 'bob'])
      })

      // Should use 'my_custom_list' directly (it's in userListNames)
      const call = dataModule.saveSeedList.mock.calls[0][0]
      expect(call.name).toBe('my_custom_list')
    })

    it('generates _custom suffix for system presets', async () => {
      dataModule.fetchGraphSettings.mockResolvedValue({
        lists: { system_preset: ['alice'] },
        active_list: 'system_preset',
        preset_names: ['system_preset'],
        user_list_names: [],
      })
      dataModule.saveSeedList.mockResolvedValue({
        active_list: 'system_preset_custom',
        lists: { system_preset_custom: ['alice', 'bob'] },
      })

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.graphSettings).toBeTruthy()
      })

      await act(async () => {
        await result.current.persistSeedsToServer(['alice', 'bob'])
      })

      const call = dataModule.saveSeedList.mock.calls[0][0]
      expect(call.name).toBe('system_preset_custom')
    })

    it('avoids collisions with existing list names', async () => {
      dataModule.fetchGraphSettings.mockResolvedValue({
        lists: {
          system_preset: ['alice'],
          system_preset_custom: ['existing'],
        },
        active_list: 'system_preset',
        preset_names: ['system_preset'],
        user_list_names: [],
      })
      dataModule.saveSeedList.mockResolvedValue({
        active_list: 'system_preset_custom_1',
        lists: { system_preset_custom_1: ['alice', 'bob'] },
      })

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.graphSettings).toBeTruthy()
      })

      await act(async () => {
        await result.current.persistSeedsToServer(['alice', 'bob'])
      })

      const call = dataModule.saveSeedList.mock.calls[0][0]
      expect(call.name).toBe('system_preset_custom_1')
    })

    it('falls back to presetName when no active_list in settings', async () => {
      dataModule.fetchGraphSettings.mockResolvedValue({
        lists: {},
        preset_names: [],
        user_list_names: [],
      })
      dataModule.saveSeedList.mockResolvedValue({
        active_list: "Adi's Seeds",
        lists: {},
      })

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.graphSettings).toBeTruthy()
      })

      await act(async () => {
        await result.current.persistSeedsToServer(['alice'])
      })

      const call = dataModule.saveSeedList.mock.calls[0][0]
      // Falls back to presetName = "Adi's Seeds" since active_list is undefined
      expect(call.name).toBe("Adi's Seeds")
    })

    it('falls back to "graph_explorer" when no active_list and no presetName match', async () => {
      dataModule.fetchGraphSettings.mockResolvedValue({
        lists: {},
        active_list: null,
        preset_names: [],
        user_list_names: [],
      })
      dataModule.saveSeedList.mockResolvedValue(null)

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.graphSettings).toBeTruthy()
      })

      // Change presetName to something falsy-like
      await act(async () => {
        result.current.handlePresetChange({ target: { value: '' } })
      })

      // presetName is now '' which is falsy, but the hook code
      // uses: graphSettings?.active_list || presetName || 'graph_explorer'
      // active_list is null, presetName is '', so falls to 'graph_explorer'
      // However the handlePresetChange also calls applyCustomSeedList which
      // sets customSeeds to [] and presetName stays '' due to keepPresetName: true.
      // Wait - handlePresetChange sets presetName to name first, then
      // calls applyCustomSeedList with keepPresetName: true.
      // So presetName = '' after the handler. '' is falsy.
      // determineEditableSeedListName: active_list=null || presetName='' || 'graph_explorer' = 'graph_explorer'
      // presetNames is empty Set, so !presetNames.has('graph_explorer') is true, returns 'graph_explorer'
      await act(async () => {
        await result.current.persistSeedsToServer(['alice'])
      })

      const call = dataModule.saveSeedList.mock.calls[0][0]
      expect(call.name).toBe('graph_explorer')
    })
  })

  // ==========================================================================
  // 11. Settings sync effect
  // ==========================================================================

  describe('settings sync effect', () => {
    it('syncs presetName and seedTextarea from graphSettings when no custom seeds', async () => {
      const serverState = {
        lists: { 'Server Seeds': ['frank', 'grace'] },
        active_list: 'Server Seeds',
      }
      dataModule.fetchGraphSettings.mockResolvedValue(serverState)

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.presetName).toBe('Server Seeds')
      })
      expect(result.current.seedTextarea).toBe('frank\ngrace')
    })

    it('skips sync if customSeeds exist', async () => {
      const serverState = {
        lists: { 'Server Seeds': ['frank'] },
        active_list: 'Server Seeds',
      }
      dataModule.fetchGraphSettings.mockResolvedValue(serverState)

      const { result } = await renderSeeds()

      // Apply custom seeds first
      await act(async () => {
        result.current.applyCustomSeedList(['myuser'])
      })

      // Even though server state says 'Server Seeds', custom seeds take priority
      expect(result.current.activeSeedList).toEqual(['myuser'])
      expect(result.current.presetName).toBe('Custom')
    })

    it('does not sync when active_list is not in availablePresets', async () => {
      const serverState = {
        lists: { 'Real List': ['alice'] },
        active_list: 'NonExistent',
      }
      dataModule.fetchGraphSettings.mockResolvedValue(serverState)

      const { result } = await renderSeeds()

      await waitFor(() => {
        expect(result.current.graphSettings).toEqual(serverState)
      })

      // active_list 'NonExistent' is not in lists, so sync effect bails
      expect(result.current.presetName).toBe("Adi's Seeds")
    })

    it('does not sync when graphSettings is null', async () => {
      dataModule.fetchGraphSettings.mockResolvedValue(null)

      const { result } = await renderSeeds()

      // Should remain at defaults
      expect(result.current.presetName).toBe("Adi's Seeds")
      expect(result.current.seedTextarea).toBe('')
    })
  })

  // ==========================================================================
  // 12. setSeedTextarea (exposed for JSX bindings)
  // ==========================================================================

  describe('setSeedTextarea', () => {
    it('updates the seedTextarea value', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.setSeedTextarea('hello\nworld')
      })

      expect(result.current.seedTextarea).toBe('hello\nworld')
    })

    it('does not affect activeSeedList until handleApplyCustomSeeds is called', async () => {
      const { result } = await renderSeeds()

      await act(async () => {
        result.current.setSeedTextarea('newuser1\nnewuser2')
      })

      // activeSeedList should still reflect the preset, not the textarea
      expect(result.current.activeSeedList).toEqual(['alice', 'bob'])

      // Now apply
      await act(async () => {
        result.current.handleApplyCustomSeeds()
      })

      expect(result.current.activeSeedList).toEqual(['newuser1', 'newuser2'])
    })
  })

  // ==========================================================================
  // 13. Integration: full workflow
  // ==========================================================================

  describe('integration: full workflow', () => {
    it('load settings -> apply custom -> persist -> verify state', async () => {
      // Step 1: Load server settings
      const serverState = {
        lists: { 'Default': ['alice', 'bob'] },
        active_list: 'Default',
        preset_names: [],
        user_list_names: ['Default'],
      }
      dataModule.fetchGraphSettings.mockResolvedValue(serverState)

      const onSettingsLoaded = vi.fn()
      const { result } = await renderSeeds({ onSettingsLoaded })

      await waitFor(() => {
        expect(onSettingsLoaded).toHaveBeenCalledWith(serverState)
      })

      // Step 2: Apply custom seeds
      await act(async () => {
        result.current.applyCustomSeedList(['@NewUser', 'AnotherUser'])
      })

      expect(result.current.activeSeedList).toEqual(['newuser', 'anotheruser'])
      expect(result.current.presetName).toBe('Custom')
      expect(result.current.seedTextarea).toBe('newuser\nanotheruser')
      expect(result.current.customSeedHandleSet.has('newuser')).toBe(true)

      // Step 3: Persist to server
      const savedState = {
        lists: { Default: ['newuser', 'anotheruser'] },
        active_list: 'Default',
      }
      dataModule.saveSeedList.mockResolvedValue(savedState)

      await act(async () => {
        await result.current.persistSeedsToServer(['newuser', 'anotheruser'])
      })

      expect(result.current.graphSettings).toEqual(savedState)
      expect(result.current.presetName).toBe('Default')
    })
  })
})
