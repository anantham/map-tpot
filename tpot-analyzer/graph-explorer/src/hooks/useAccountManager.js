/**
 * Custom hook for account validation and autocomplete.
 *
 * Manages the "My Account" input: raw input, validation against
 * the backend snapshot, autocomplete suggestions, and keyboard navigation.
 *
 * @param {Object} options
 * @param {string} options.initialInput  - Pre-filled account handle
 * @param {boolean} options.initialValid - Whether the initial handle is validated
 * @param {Function} options.onAccountChange - Called when account state changes (validate/clear/pending)
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { searchAccounts } from '../accountsApi'

const stripShadowPrefix = (value = '') => String(value).replace(/^shadow:/i, '')
const normalizeHandle = (value) => {
  if (!value) return null
  return stripShadowPrefix(value).toLowerCase()
}

export function useAccountManager({ initialInput = '', initialValid = false, onAccountChange }) {
  // Use ref for callback to avoid stale closures — callers can pass a callback
  // that isn't stable yet (e.g., depends on state defined after this hook call)
  const onChangeRef = useRef(onAccountChange)
  const fireChange = useCallback(() => { onChangeRef.current?.() }, [])
  useEffect(() => { onChangeRef.current = onAccountChange }, [onAccountChange])

  const [validatedAccount, setValidatedAccount] = useState(initialValid ? initialInput : '')
  const [myAccountInput, setMyAccountInput] = useState(initialInput)
  const [myAccountValid, setMyAccountValid] = useState(Boolean(initialInput) && initialValid)
  const [myAccountError, setMyAccountError] = useState(null)
  const [accountSuggestions, setAccountSuggestions] = useState([])
  const [showAccountSuggestions, setShowAccountSuggestions] = useState(false)
  const [accountSuggestionIndex, setAccountSuggestionIndex] = useState(-1)

  const autocompleteTimeoutRef = useRef(null)

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (autocompleteTimeoutRef.current) {
        clearTimeout(autocompleteTimeoutRef.current)
      }
    }
  }, [])

  const applyValidatedAccount = useCallback((username) => {
    const cleaned = stripShadowPrefix(username || '')
    setValidatedAccount(cleaned)
    setMyAccountInput(cleaned)
    setMyAccountValid(true)
    setMyAccountError(null)
    setAccountSuggestions([])
    setShowAccountSuggestions(false)
    setAccountSuggestionIndex(-1)
    fireChange()
  }, [fireChange])

  const markAccountPending = useCallback(() => {
    if (validatedAccount || myAccountValid) {
      setValidatedAccount('')
      setMyAccountValid(false)
      fireChange()
    }
  }, [validatedAccount, myAccountValid, fireChange])

  const clearAccount = useCallback(() => {
    setMyAccountInput('')
    setMyAccountError(null)
    setAccountSuggestions([])
    setShowAccountSuggestions(false)
    setAccountSuggestionIndex(-1)
    setValidatedAccount('')
    setMyAccountValid(false)
    fireChange()
  }, [fireChange])

  const fetchAccountSuggestions = useCallback(async (query) => {
    try {
      const results = await searchAccounts({ q: query, limit: 10 })
      setAccountSuggestions(results)
      setShowAccountSuggestions(Array.isArray(results) && results.length > 0)
    } catch (err) {
      console.error('Account autocomplete error:', err)
      setAccountSuggestions([])
      setShowAccountSuggestions(false)
    }
  }, [])

  const validateAccountInput = useCallback(async (value) => {
    const candidate = stripShadowPrefix((value || '').trim())
    if (!candidate) {
      setMyAccountError('Enter your Twitter handle')
      clearAccount()
      return false
    }

    try {
      const results = await searchAccounts({ q: candidate, limit: 10 })
      const match = Array.isArray(results) && results.find(
        (item) => normalizeHandle(item.username) === candidate.toLowerCase()
      )
      if (match) {
        applyValidatedAccount(match.username)
        return true
      }
      setMyAccountError(`@${candidate} is not part of this snapshot yet.`)
      markAccountPending()
      return false
    } catch (err) {
      console.error('Account validation error:', err)
      setMyAccountError('Unable to validate handle. Please try again.')
      markAccountPending()
      return false
    }
  }, [applyValidatedAccount, markAccountPending, clearAccount])

  const selectAccountSuggestion = useCallback((item) => {
    if (!item) return
    applyValidatedAccount(item.username)
  }, [applyValidatedAccount])

  const handleAccountInputChange = useCallback((e) => {
    const raw = e.target.value.replace(/^@/, '')
    setMyAccountInput(raw)
    setMyAccountError(null)
    setAccountSuggestionIndex(-1)
    if (!raw.trim()) {
      markAccountPending()
      setAccountSuggestions([])
      setShowAccountSuggestions(false)
      return
    }
    markAccountPending()
    if (autocompleteTimeoutRef.current) {
      clearTimeout(autocompleteTimeoutRef.current)
    }
    autocompleteTimeoutRef.current = setTimeout(() => {
      fetchAccountSuggestions(raw.trim())
    }, 200)
  }, [markAccountPending, fetchAccountSuggestions])

  const handleAccountKeyDown = useCallback((e) => {
    if (showAccountSuggestions && accountSuggestions.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setAccountSuggestionIndex((prev) =>
          prev < accountSuggestions.length - 1 ? prev + 1 : prev
        )
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setAccountSuggestionIndex((prev) => (prev > 0 ? prev - 1 : -1))
        return
      }
      if (e.key === 'Enter' && accountSuggestionIndex >= 0) {
        e.preventDefault()
        selectAccountSuggestion(accountSuggestions[accountSuggestionIndex])
        return
      }
      if (e.key === 'Escape') {
        setShowAccountSuggestions(false)
        setAccountSuggestionIndex(-1)
        return
      }
    }

    if (e.key === 'Enter') {
      e.preventDefault()
      validateAccountInput(myAccountInput)
    }
  }, [showAccountSuggestions, accountSuggestions, accountSuggestionIndex, selectAccountSuggestion, validateAccountInput, myAccountInput])

  const handleAccountBlur = useCallback(() => {
    setTimeout(() => setShowAccountSuggestions(false), 150)
  }, [])

  return {
    // State
    validatedAccount,
    myAccountInput,
    myAccountValid,
    myAccountError,
    accountSuggestions,
    showAccountSuggestions,
    accountSuggestionIndex,
    setAccountSuggestionIndex,
    // Handlers
    handleAccountInputChange,
    handleAccountKeyDown,
    handleAccountBlur,
    validateAccountInput,
    selectAccountSuggestion,
    clearAccount,
  }
}
