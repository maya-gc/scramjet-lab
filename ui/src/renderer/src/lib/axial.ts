import type { GeometryDerived, StationData, Stations } from './types'

export const STATION_ORDER = [
  'capture',
  'isolator_in',
  'isolator_out',
  'combustor_in',
  'combustor_out',
  'nozzle_exit'
] as const

export const STATION_LABEL: Record<string, string> = {
  capture: 'Capture',
  isolator_in: 'Isolator in',
  isolator_out: 'Isolator out',
  combustor_in: 'Combustor in',
  combustor_out: 'Combustor out',
  nozzle_exit: 'Nozzle exit'
}

export interface FlowStationDatum {
  x: number
  M: number | null
  p: number | null
  T: number | null
  p0: number | null
  velocity: number | null
  station: string
}

export function axialProfile(stations: Stations): FlowStationDatum[] {
  const out: FlowStationDatum[] = []
  for (const key of STATION_ORDER) {
    const s: StationData | null = stations?.[key]
    out.push({
      x: s?.x ?? NaN,
      M: s?.M_massavg ?? null,
      p: s?.p_massavg ?? null,
      T: s?.T_massavg ?? null,
      p0: s?.p0_massavg ?? null,
      velocity: s?.Vx_massavg ?? null,
      station: STATION_LABEL[key]
    })
  }
  return out.filter((d) => Number.isFinite(d.x) && d.M != null)
}

export interface RegionRange {
  id: string
  label: string
  start: number
  end: number
}

export function combustorRange(
  derived: GeometryDerived | null | undefined
): RegionRange | null {
  if (!derived) return null
  const start = derived.x_isolator_end
  const end = derived.x_combustor_end
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null
  return { id: 'combustor', label: 'Combustor', start, end }
}