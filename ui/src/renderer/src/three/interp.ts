export interface Interpolant {
  x: number[]
  y: number[]
  eval(x: number): number
}

export function makeInterpolant(xsSorted: number[], ys: number[]): Interpolant {
  if (xsSorted.length === 0) {
    return { x: [0], y: [0], eval: () => 0 }
  }
  if (xsSorted.length === 1) {
    const v = ys[0]
    return { x: xsSorted, y: ys, eval: () => v }
  }
  return {
    x: xsSorted,
    y: ys,
    eval(x) {
      const X = this.x
      if (x <= X[0]) return this.y[0]
      const last = X.length - 1
      if (x >= X[last]) return this.y[last]
      for (let i = 0; i < last; i++) {
        if (x >= X[i] && x <= X[i + 1]) {
          const f = (x - X[i]) / (X[i + 1] - X[i])
          return this.y[i] + (this.y[i + 1] - this.y[i]) * f
        }
      }
      return this.y[last]
    }
  }
}

/** Time (sim seconds) to cross the whole duct at the given velocity profile.
 *  Used as the GPU cycle period so one shader cycle == one duct traversal. */
export function crossingTime(
  vel: Interpolant,
  xMax: number,
  scale: number,
  n = 256
): number {
  let t = 0
  for (let i = 1; i <= n; i++) {
    const x0 = ((i - 1) / n) * xMax
    const x1 = (i / n) * xMax
    const v = vel.eval((x0 + x1) / 2)
    t += (x1 - x0) / Math.max(v, 1) / scale
  }
  return t
}
