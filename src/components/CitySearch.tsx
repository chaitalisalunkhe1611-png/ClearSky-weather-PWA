import { useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { LoaderCircle, MapPin, Search, X } from 'lucide-react'
import { searchCities, type WeatherLocation } from '../lib/api'

interface CitySearchProps {
  onSelect: (location: WeatherLocation) => void
  className?: string
}

function locationLabel(location: WeatherLocation): string {
  return [location.admin1, location.country].filter(Boolean).join(', ')
}

export function CitySearch({ onSelect, className = '' }: CitySearchProps) {
  const inputId = useId()
  const listId = useId()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<WeatherLocation[]>([])
  const [activeIndex, setActiveIndex] = useState(-1)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [dismissed, setDismissed] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    function focusSearch(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', focusSearch)
    return () => window.removeEventListener('keydown', focusSearch)
  }, [])

  useEffect(() => {
    const trimmed = query.trim()
    setActiveIndex(-1)
    if (trimmed.length < 2) {
      setResults([])
      setLoading(false)
      setMessage('')
      controllerRef.current?.abort()
      return
    }

    setMessage('')
    const timer = window.setTimeout(() => {
      const controller = new AbortController()
      controllerRef.current?.abort()
      controllerRef.current = controller
      setLoading(true)
      void searchCities(trimmed, controller.signal)
        .then((cities) => {
          setResults(cities)
          setMessage(cities.length === 0 ? 'No places found. Try another city.' : '')
        })
        .catch((error: unknown) => {
          if (error instanceof Error && error.name === 'AbortError') return
          setResults([])
          setMessage('City search is unavailable right now. Please try again.')
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false)
        })
    }, 300)

    return () => {
      window.clearTimeout(timer)
      controllerRef.current?.abort()
    }
  }, [query])

  function choose(location: WeatherLocation) {
    setQuery('')
    setResults([])
    setMessage('')
    setActiveIndex(-1)
    setDismissed(false)
    onSelect(location)
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' && results.length > 0) {
      event.preventDefault()
      setActiveIndex((index) => (index + 1) % results.length)
    } else if (event.key === 'ArrowUp' && results.length > 0) {
      event.preventDefault()
      setActiveIndex((index) => (index - 1 + results.length) % results.length)
    } else if (event.key === 'Enter' && activeIndex >= 0 && results[activeIndex]) {
      event.preventDefault()
      choose(results[activeIndex])
    } else if (event.key === 'Escape') {
      controllerRef.current?.abort()
      setLoading(false)
      setResults([])
      setMessage('')
      setActiveIndex(-1)
      setDismissed(true)
    }
  }

  const expanded = query.trim().length >= 2 && !dismissed && (loading || results.length > 0 || Boolean(message))

  return (
    <div className={`city-search ${className}`}>
      <label className="sr-only" htmlFor={inputId}>Search for a city</label>
      <div className="search-field">
        <Search size={18} aria-hidden="true" className="search-leading-icon" />
        <input
          id={inputId}
          ref={inputRef}
          type="search"
          autoComplete="off"
          role="combobox"
          aria-label="Search for a city"
          aria-autocomplete="list"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-activedescendant={activeIndex >= 0 ? `${listId}-option-${activeIndex}` : undefined}
          aria-busy={loading}
          placeholder="Search a city or town…"
          value={query}
          onChange={(event) => { setDismissed(false); setQuery(event.target.value) }}
          onKeyDown={handleKeyDown}
        />
        {loading ? <LoaderCircle size={17} className="search-spinner" aria-label="Searching" /> : null}
        {!loading && query ? (
          <button className="search-clear" type="button" aria-label="Clear search" onClick={() => setQuery('')}>
            <X size={16} />
          </button>
        ) : null}
        <kbd className="search-shortcut" aria-hidden="true">⌘ K</kbd>
      </div>
      <div className="search-results" id={listId} role="listbox" aria-label="City search results" hidden={!expanded}>
        {loading ? <p className="search-status" role="status">Finding places…</p> : null}
        {!loading && results.map((location, index) => (
          <div
            id={`${listId}-option-${index}`}
            className={`search-option ${index === activeIndex ? 'is-active' : ''}`}
            key={`${location.latitude}-${location.longitude}`}
            role="option"
            aria-selected={index === activeIndex}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => choose(location)}
            onMouseEnter={() => setActiveIndex(index)}
          >
            <span className="search-option-pin"><MapPin size={17} aria-hidden="true" /></span>
            <span className="search-option-copy">
              <strong>{location.name}</strong>
              <small>{locationLabel(location) || 'Location'}</small>
            </span>
            <span className="search-option-arrow" aria-hidden="true">↗</span>
          </div>
        ))}
        {!loading && message ? <p className="search-status" role="status">{message}</p> : null}
      </div>
    </div>
  )
}
