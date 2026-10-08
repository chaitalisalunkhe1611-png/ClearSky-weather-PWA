import {
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudLightning,
  CloudRain,
  CloudSnow,
  CloudSun,
  Moon,
  Sun,
  type LucideIcon,
} from 'lucide-react'
import { describeWeather, type WeatherKind } from '../lib/wmo'

const iconForKind: Record<WeatherKind, LucideIcon> = {
  sun: Sun,
  'partly-cloudy': CloudSun,
  cloud: Cloud,
  fog: CloudFog,
  drizzle: CloudDrizzle,
  rain: CloudRain,
  snow: CloudSnow,
  storm: CloudLightning,
}

interface WeatherIconProps {
  code: number | null | undefined
  size?: number
  className?: string
  night?: boolean
}

export function WeatherIcon({ code, size = 40, className, night = false }: WeatherIconProps) {
  const description = describeWeather(code)
  const Icon = night && description.kind === 'sun' ? Moon : iconForKind[description.kind]
  return <Icon aria-hidden="true" focusable="false" size={size} className={className} strokeWidth={1.7} />
}
