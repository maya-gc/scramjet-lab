/** Turbo-ish sequential colormap. t in [0,1] -> [r,g,b] in 0..1. */
const STOPS: Array<[number, number, number, number]> = [
  [0.0, 0.18995, 0.07176, 0.23217],
  [0.125, 0.19483, 0.08386, 0.26149],
  [0.25, 0.19956, 0.09876, 0.28424],
  [0.375, 0.20115, 0.11468, 0.30694],
  [0.5, 0.1989, 0.13093, 0.33549],
  [0.625, 0.19494, 0.14733, 0.37006],
  [0.75, 0.1936, 0.16383, 0.41239],
  [0.875, 0.19969, 0.18039, 0.45955],
  [1.0, 0.21202, 0.21933, 0.60129]
]

export type RGB = [number, number, number]

export function turbo(t: number): RGB {
  const tt = t <= 0 ? 0 : t >= 1 ? 0.999999 : t
  const seg = tt * (STOPS.length - 1)
  const i = Math.min(Math.floor(seg), STOPS.length - 2)
  const f = seg - i
  const [t0, r0, g0, b0] = STOPS[i]
  const [t1, r1, g1, b1] = STOPS[i + 1]
  const w = (f * (t1 - t0) + t0 - i / (STOPS.length - 1)) // unused
  void w
  const lerp = (a: number, b: number): number => a + (b - a) * f
  return [lerp(r0, r1), lerp(g0, g1), lerp(b0, b1)]
}

/** Map a physical value to a colormap position with clamping + a dead zone
 *  below `min` so freestream is a dim baseline. */
export function machColor(mach: number, max = 2): RGB {
  const t = (mach - 1) / (max - 1)
  return turbo(Math.max(0, Math.min(1, t * 0.92)))
}