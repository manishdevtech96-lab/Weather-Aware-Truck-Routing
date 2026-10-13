import { useEffect, useRef, useState } from 'react'
import { suggestPlaces } from './api'

export default function PlaceField({ label, value, onChange, onSelect }) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const requestId = useRef(0)
  const selectedLabel = useRef('')

  useEffect(() => {
    const query = value.trim()
    if (!open || query.length < 2 || query === selectedLabel.current) {
      setSuggestions([])
      return undefined
    }

    const currentId = requestId.current + 1
    requestId.current = currentId
    const timer = setTimeout(async () => {
      try {
        const places = await suggestPlaces(query)
        if (currentId === requestId.current) setSuggestions(places)
      } catch {
        if (currentId === requestId.current) setSuggestions([])
      }
    }, 250)

    return () => clearTimeout(timer)
  }, [open, value])

  function choose(place) {
    selectedLabel.current = place.label
    setSuggestions([])
    setOpen(false)
    onSelect(place)
  }

  return (
    <div className="place-field">
      <label>
        {label}
        <input
          required
          value={value}
          autoComplete="off"
          placeholder="City, address, or place"
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onChange={(event) => {
            selectedLabel.current = ''
            onChange(event.target.value)
            setOpen(true)
          }}
        />
      </label>
      {open && suggestions.length > 0 && (
        <ul className="suggestions">
          {suggestions.map((place) => (
            <li key={`${place.latitude},${place.longitude},${place.label}`}>
              <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => choose(place)}>
                {place.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
