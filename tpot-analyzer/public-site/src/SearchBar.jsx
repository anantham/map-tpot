import { useState, useRef, useCallback, useEffect } from 'react'
import { SEARCH_JSON_ENDPOINT, fetchJson } from './dataEndpoints'

export default function SearchBar({ onResult }) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [highlightIdx, setHighlightIdx] = useState(-1)
  const searchCache = useRef(null)
  const inputRef = useRef(null)

  const loadPromise = useRef(null)

  const loadSearchData = useCallback(async () => {
    if (searchCache.current) return searchCache.current
    if (loadPromise.current) return loadPromise.current

    loadPromise.current = fetchJson(SEARCH_JSON_ENDPOINT)
      .then(data => {
        searchCache.current = data
        return data
      })
      .catch(err => {
        console.error('Failed to load search.json:', err)
        loadPromise.current = null
        return null
      })

    return loadPromise.current
  }, [])

  const normalize = (input) => input.replace(/^@/, '').trim().toLowerCase()

  const updateSuggestions = useCallback(async (raw) => {
    const term = normalize(raw)
    if (!term) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }

    const data = await loadSearchData()
    if (!data) return

    const matches = []
    for (const handle of Object.keys(data)) {
      if (handle.startsWith(term)) {
        matches.push({ handle, ...data[handle] })
        if (matches.length >= 8) break
      }
    }
    setSuggestions(matches)
    setShowSuggestions(matches.length > 0)
    setHighlightIdx(-1)
  }, [loadSearchData])

  const handleChange = (e) => {
    const val = e.target.value
    setQuery(val)
    updateSuggestions(val)
  }

  const submitHandle = useCallback(async (raw) => {
    const term = normalize(raw)
    if (!term) return

    const data = await loadSearchData()
    if (!data) return

    const entry = data[term]
    if (entry) {
      onResult({ handle: term, ...entry })
    } else {
      onResult({ handle: term, tier: 'not_found' })
    }
    setSuggestions([])
    setShowSuggestions(false)
    setQuery('')
  }, [loadSearchData, onResult])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (highlightIdx >= 0 && highlightIdx < suggestions.length) {
      submitHandle(suggestions[highlightIdx].handle)
    } else {
      submitHandle(query)
    }
  }

  const handleKeyDown = (e) => {
    if (!showSuggestions) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightIdx(i => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightIdx(i => Math.max(i - 1, -1))
    } else if (e.key === 'Escape') {
      setShowSuggestions(false)
    }
  }

  const handleSuggestionClick = (handle) => {
    submitHandle(handle)
  }

  // Close suggestions on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (inputRef.current && !inputRef.current.contains(e.target)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <form className="search-bar" onSubmit={handleSubmit} ref={inputRef}>
      <div className="search-input-wrap">
        <input
          type="text"
          className="search-input"
          placeholder="Search @handle..."
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
          autoComplete="off"
          spellCheck="false"
        />
        <button type="submit" className="search-btn">Search</button>
      </div>

      {showSuggestions && (
        <ul className="suggestions">
          {suggestions.map((s, i) => (
            <li
              key={s.handle}
              className={`suggestion${i === highlightIdx ? ' highlighted' : ''}`}
              onMouseDown={() => handleSuggestionClick(s.handle)}
              onMouseEnter={() => setHighlightIdx(i)}
            >
              <span className="suggestion-handle">@{s.handle}</span>
              <span className={`suggestion-tier tier-${s.tier}`}>{s.tier}</span>
            </li>
          ))}
        </ul>
      )}
    </form>
  )
}
