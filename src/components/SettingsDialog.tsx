import { useEffect, useRef, type KeyboardEvent } from 'react'
import { Check, Monitor, Moon, Sun, X } from 'lucide-react'
import type { Preferences } from '../lib/storage'

interface SettingsDialogProps {
  preferences: Preferences
  onChange: (preferences: Preferences) => void
  onClose: () => void
}

export function SettingsDialog({ preferences, onChange, onClose }: SettingsDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeButtonRef.current?.focus()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [])

  function trapFocus(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      onClose()
      return
    }
    if (event.key !== 'Tab') return
    const dialog = event.currentTarget
    const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button, input, [tabindex="0"]'))
      .filter((element) => !element.hasAttribute('disabled'))
    if (focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const temperatureOptions = [
    { value: 'celsius', label: 'Celsius', short: '°C' },
    { value: 'fahrenheit', label: 'Fahrenheit', short: '°F' },
  ] as const
  const windOptions = [
    { value: 'kmh', label: 'Kilometres per hour', short: 'km/h' },
    { value: 'mph', label: 'Miles per hour', short: 'mph' },
  ] as const
  const themeOptions = [
    { value: 'system', label: 'System', Icon: Monitor },
    { value: 'light', label: 'Light', Icon: Sun },
    { value: 'dark', label: 'Dark', Icon: Moon },
  ] as const

  return (
    <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        className="settings-dialog glass-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        onKeyDown={trapFocus}
      >
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">MAKE IT YOURS</span>
            <h2 id="settings-title">Settings</h2>
          </div>
          <button className="icon-button close-button" type="button" aria-label="Close settings" onClick={onClose} ref={closeButtonRef}>
            <X size={19} />
          </button>
        </div>

        <fieldset className="setting-group">
          <legend>Temperature</legend>
          <div className="choice-row">
            {temperatureOptions.map((option) => (
              <button
                type="button"
                key={option.value}
                className={`choice-button ${preferences.temperatureUnit === option.value ? 'is-selected' : ''}`}
                aria-pressed={preferences.temperatureUnit === option.value}
                onClick={() => onChange({ ...preferences, temperatureUnit: option.value })}
              >
                <span>{option.label}</span><strong>{option.short}</strong>
                {preferences.temperatureUnit === option.value ? <Check size={15} aria-hidden="true" /> : null}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="setting-group">
          <legend>Wind speed</legend>
          <div className="choice-row">
            {windOptions.map((option) => (
              <button
                type="button"
                key={option.value}
                className={`choice-button ${preferences.windUnit === option.value ? 'is-selected' : ''}`}
                aria-pressed={preferences.windUnit === option.value}
                onClick={() => onChange({ ...preferences, windUnit: option.value })}
              >
                <span>{option.label}</span><strong>{option.short}</strong>
                {preferences.windUnit === option.value ? <Check size={15} aria-hidden="true" /> : null}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="setting-group">
          <legend>Appearance</legend>
          <div className="theme-options">
            {themeOptions.map(({ value, label, Icon }) => (
              <button
                type="button"
                key={value}
                className={`theme-option ${preferences.theme === value ? 'is-selected' : ''}`}
                aria-pressed={preferences.theme === value}
                onClick={() => onChange({ ...preferences, theme: value })}
              >
                <Icon size={19} aria-hidden="true" />
                <span>{label}</span>
                {preferences.theme === value ? <Check size={14} className="theme-check" aria-hidden="true" /> : null}
              </button>
            ))}
          </div>
        </fieldset>

        <p className="settings-privacy"><span className="privacy-dot" /> Preferences stay on this device.</p>
      </div>
    </div>
  )
}
