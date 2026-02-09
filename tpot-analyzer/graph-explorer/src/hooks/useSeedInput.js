/**
 * Custom hook for seed input with autocomplete.
 *
 * Manages the seed input field: typing, debounced autocomplete search,
 * keyboard navigation (arrow keys / enter / escape), add/remove seeds.
 *
 * @param {Object} options
 * @param {string[]} options.seeds    - Current seed list (external state)
 * @param {Function} options.setSeeds - Setter for the seed list
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { searchAccounts } from '../accountsApi'

export function useSeedInput({ seeds, setSeeds }) {
  const [seedInput, setSeedInput] = useState('')
  const [autocompleteResults, setAutocompleteResults] = useState([])
  const [showAutocomplete, setShowAutocomplete] = useState(false)
  const [selectedAutocompleteIndex, setSelectedAutocompleteIndex] = useState(-1)

  const autocompleteTimeoutRef = useRef(null)

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (autocompleteTimeoutRef.current) {
        clearTimeout(autocompleteTimeoutRef.current)
      }
    }
  }, [])

  const fetchAutocomplete = useCallback(async (query) => {
    if (!query || query.length < 1) {
      setAutocompleteResults([])
      setShowAutocomplete(false)
      return
    }
    try {
      const results = await searchAccounts({ q: query, limit: 10 })
      setAutocompleteResults(results)
      setShowAutocomplete(Array.isArray(results) && results.length > 0)
    } catch (err) {
      console.error('Autocomplete error:', err)
      setAutocompleteResults([])
      setShowAutocomplete(false)
    }
  }, [])

  const clearInput = useCallback(() => {
    setSeedInput('')
    setAutocompleteResults([])
    setShowAutocomplete(false)
    setSelectedAutocompleteIndex(-1)
  }, [])

  const addSeed = useCallback((e) => {
    e?.preventDefault()
    const trimmed = seedInput.trim()
    if (trimmed && !seeds.includes(trimmed)) {
      setSeeds([...seeds, trimmed])
    }
    clearInput()
  }, [seedInput, seeds, setSeeds, clearInput])

  const removeSeed = useCallback((seed) => {
    setSeeds(seeds.filter(s => s !== seed))
  }, [seeds, setSeeds])

  const selectAutocompleteItem = useCallback((item) => {
    if (item && !seeds.includes(item.username)) {
      setSeeds([...seeds, item.username])
    }
    clearInput()
  }, [seeds, setSeeds, clearInput])

  const handleInputChange = useCallback((e) => {
    const value = e.target.value
    setSeedInput(value)
    setSelectedAutocompleteIndex(-1)

    if (autocompleteTimeoutRef.current) {
      clearTimeout(autocompleteTimeoutRef.current)
    }

    if (value.trim()) {
      autocompleteTimeoutRef.current = setTimeout(() => {
        fetchAutocomplete(value.trim())
      }, 200)
    } else {
      setAutocompleteResults([])
      setShowAutocomplete(false)
    }
  }, [fetchAutocomplete])

  const handleKeyDown = useCallback((e) => {
    if (!showAutocomplete) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedAutocompleteIndex(prev =>
        prev < autocompleteResults.length - 1 ? prev + 1 : prev
      )
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedAutocompleteIndex(prev => prev > -1 ? prev - 1 : -1)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (selectedAutocompleteIndex >= 0) {
        selectAutocompleteItem(autocompleteResults[selectedAutocompleteIndex])
      } else {
        addSeed(e)
      }
    } else if (e.key === 'Escape') {
      setShowAutocomplete(false)
      setSelectedAutocompleteIndex(-1)
    }
  }, [showAutocomplete, autocompleteResults, selectedAutocompleteIndex, selectAutocompleteItem, addSeed])

  return {
    seedInput,
    autocompleteResults,
    showAutocomplete,
    selectedAutocompleteIndex,
    handleInputChange,
    handleKeyDown,
    addSeed,
    removeSeed,
    selectAutocompleteItem,
  }
}
