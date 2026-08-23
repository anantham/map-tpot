import { useId, useMemo, useState } from 'react'

import { rankTagMatches } from './tagSearch'

export default function TagAutocomplete({
  disabled = false,
  onChange,
  onSelect,
  tags = [],
  value = '',
}) {
  const inputId = useId()
  const listId = useId()
  const [activeIndex, setActiveIndex] = useState(-1)
  const [open, setOpen] = useState(false)
  const matches = useMemo(() => rankTagMatches(value, tags), [tags, value])
  const showOptions = open && matches.length > 0

  const choose = (tag) => {
    onChange?.(tag)
    onSelect?.(tag)
    setActiveIndex(-1)
    setOpen(false)
  }

  return (
    <div
      className="tag-autocomplete"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
      }}
    >
      <label htmlFor={inputId}>Find or create a tag</label>
      <input
        id={inputId}
        role="combobox"
        aria-autocomplete="list"
        aria-activedescendant={
          showOptions && activeIndex >= 0 ? `${listId}-option-${activeIndex}` : undefined
        }
        aria-controls={listId}
        aria-expanded={showOptions}
        autoComplete="off"
        disabled={disabled}
        onChange={(event) => {
          onChange?.(event.target.value)
          setActiveIndex(-1)
          setOpen(true)
        }}
        onFocus={() => {
          setActiveIndex(-1)
          setOpen(true)
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && matches.length > 0) {
            event.preventDefault()
            setOpen(true)
            setActiveIndex((current) => Math.min(current + 1, matches.length - 1))
          } else if (event.key === 'ArrowUp' && matches.length > 0) {
            event.preventDefault()
            setOpen(true)
            setActiveIndex((current) => (
              current <= 0 ? matches.length - 1 : current - 1
            ))
          } else if (event.key === 'Enter' && showOptions && activeIndex >= 0) {
            event.preventDefault()
            choose(matches[activeIndex])
          } else if (event.key === 'Escape') {
            setActiveIndex(-1)
            setOpen(false)
          }
        }}
        placeholder="e.g. AI alignment"
        value={value}
      />
      {showOptions && (
        <div className="tag-autocomplete-options" id={listId} role="listbox">
          {matches.map((tag, index) => (
            <button
              key={tag}
              id={`${listId}-option-${index}`}
              type="button"
              role="option"
              className={activeIndex === index ? 'is-keyboard-active' : undefined}
              aria-selected={activeIndex === index || value === tag}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(tag)}
            >
              {tag}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
