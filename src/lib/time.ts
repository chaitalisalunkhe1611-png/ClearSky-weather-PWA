export function hourLabel(dateTime: string, hour12 = true): string {
  const time = dateTime.split('T')[1]
  if (!time) return dateTime
  const [hourPart, minutePart] = time.split(':')
  const hour = Number(hourPart)
  const minute = minutePart ?? '00'
  if (!Number.isFinite(hour)) return time
  if (!hour12) return `${String(hour).padStart(2, '0')}:${minute}`
  const suffix = hour >= 12 ? 'PM' : 'AM'
  const displayHour = hour % 12 || 12
  return minute === '00' ? `${displayHour} ${suffix}` : `${displayHour}:${minute} ${suffix}`
}

export function weekdayLabel(date: string, style: 'short' | 'long' = 'short'): string {
  const [year, month, day] = date.split('-').map(Number)
  if (!year || !month || !day) return date
  // UTC avoids shifting an API-local calendar day in the browser's timezone.
  return new Intl.DateTimeFormat('en', { weekday: style, timeZone: 'UTC' }).format(new Date(Date.UTC(year, month - 1, day)))
}

export function localDateTimeLabel(dateTime: string, options?: Intl.DateTimeFormatOptions): string {
  const [date, time = '00:00'] = dateTime.split('T')
  const [year, month, day] = date.split('-').map(Number)
  const [hour, minute] = time.split(':').map(Number)
  if (!year || !month || !day) return dateTime
  const value = new Date(Date.UTC(year, month - 1, day, hour, minute))
  return new Intl.DateTimeFormat('en', {
    weekday: 'long', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'UTC', ...options,
  }).format(value)
}

export function isDaylight(time: string, sunrise: string | null | undefined, sunset: string | null | undefined): boolean {
  if (!sunrise || !sunset) return true
  const localTime = time.slice(0, 16)
  return localTime >= sunrise.slice(0, 16) && localTime <= sunset.slice(0, 16)
}
