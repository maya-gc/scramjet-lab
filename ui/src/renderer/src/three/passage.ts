import type { GeometryPayload } from '../lib/types'

/** Piecewise-linear access to the engine passage (scaled coordinates). */
export interface Passage {
  lower: number[][]
  upper: number[][]
  strut: number[][] | null
  xMax: number
  yMax: number
  span: number
  lowerY(x: number): number
  upperY(x: number): number
  /** Blocked vertical interval [y0,y1] at x inside the strut, else null. */
  strutBlock(x: number): [number, number] | null
  sampleY(x: number): [number, number]
}

function interp(poly: number[][], x: number, fallback: number): number {
  if (poly.length === 0) return fallback
  if (x <= poly[0][0]) return poly[0][1]
  const last = poly[poly.length - 1]
  if (x >= last[0]) return last[1]
  for (let i = 0; i < poly.length - 1; i++) {
    const a = poly[i]
    const b = poly[i + 1]
    if (x >= a[0] && x <= b[0]) {
      const f = b[0] - a[0] > 1e-12 ? (x - a[0]) / (b[0] - a[0]) : 0
      return a[1] + (b[1] - a[1]) * f
    }
  }
  return fallback
}

export function passageFromGeo(geo: GeometryPayload): Passage {
  const d = geo.derived
  const lower = geo.lower.map((p) => [p[0], p[1]] as [number, number])
  const upper = geo.upper.map((p) => [p[0], p[1]] as [number, number])
  const strut =
    geo.strut?.map((p) => [p[0], p[1]] as [number, number]) ?? null

  const xMax = d.L_total ?? Math.max(...lower.map((p) => p[0]))
  const yMax = d.H_capture ?? Math.max(...upper.map((p) => p[1]))
  const span = d.B ?? 0.1

  const strutX0 = strut ? Math.min(...strut.map((p) => p[0])) : null
  const strutX1 = strut ? Math.max(...strut.map((p) => p[0])) : null
  const strutY0 = strut ? Math.min(...strut.map((p) => p[1])) : null
  const strutY1 = strut ? Math.max(...strut.map((p) => p[1])) : null

  return {
    lower,
    upper,
    strut,
    xMax,
    yMax,
    span,
    lowerY: (x) => interp(lower, x, 0),
    upperY: (x) => interp(upper, x, yMax),
    strutBlock(x) {
      if (strutX0 == null || strutX1 == null) return null
      if (x >= strutX0 && x <= strutX1) return [strutY0 as number, strutY1 as number]
      return null
    },
    sampleY(x) {
      const yl = this.lowerY(x)
      const yu = this.upperY(x)
      const block = this.strutBlock(x)
      if (!block) return [yl, yu]
      // Pick the larger of the two open regions.
      const top = yu - block[1]
      const bottom = block[0] - yl
      if (top >= bottom) return [block[1], yu]
      return [yl, block[0]]
    }
  }
}