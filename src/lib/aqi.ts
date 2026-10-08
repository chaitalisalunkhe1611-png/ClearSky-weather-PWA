export interface AqiLevel {
  label: string
  detail: string
  className: string
}

export function getAqiLevel(value: number | null | undefined): AqiLevel {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return { label: 'Unavailable', detail: 'Air quality is unavailable', className: 'aqi-muted' }
  }
  if (value <= 50) return { label: 'Good', detail: 'Air quality is good', className: 'aqi-good' }
  if (value <= 100) return { label: 'Moderate', detail: 'Air quality is moderate', className: 'aqi-moderate' }
  if (value <= 150) return { label: 'Sensitive', detail: 'Unhealthy for sensitive groups', className: 'aqi-sensitive' }
  if (value <= 200) return { label: 'Unhealthy', detail: 'Air quality is unhealthy', className: 'aqi-unhealthy' }
  if (value <= 300) return { label: 'Very unhealthy', detail: 'Air quality is very unhealthy', className: 'aqi-very-unhealthy' }
  return { label: 'Hazardous', detail: 'Air quality is hazardous', className: 'aqi-hazardous' }
}
